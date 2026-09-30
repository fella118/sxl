"""The monthly collection cycle: kickoff, inbound handling, scheduled follow-ups, owner report."""

import re
from datetime import date, timedelta
from pathlib import Path

from . import templates
from .agent import Assistant, _deadline
from .store import DOC_LABELS, Store

ALLOWED_MIME = {"image/jpeg", "image/png", "image/webp", "image/gif", "application/pdf"}
MAX_FILE_BYTES = 10 * 1024 * 1024
# Days to wait before the next template reminder, by how many reminders were already sent.
NUDGE_GAP_DAYS = [3, 3, 2, 2]


class Service:
    def __init__(self, store: Store, assistant: Assistant, *, firm: str, deadline_day: int,
                 files_dir: str | Path, send=None):
        self.store = store
        self.assistant = assistant
        self.firm = firm
        self.deadline_day = deadline_day
        self.files_dir = Path(files_dir)
        self.send = send or (lambda client, text: None)  # hook for the real WhatsApp sender

    # --- calendar ----------------------------------------------------------
    def period(self) -> str:
        """Documents are collected for the month before today."""
        first = self.store.today.replace(day=1)
        prev = first - timedelta(days=1)
        return f"{prev.year:04d}-{prev.month:02d}"

    def deadline(self, period: str) -> date:
        year, month = (int(x) for x in period.split("-"))
        return _deadline(year, month, self.deadline_day)

    # --- outbound ----------------------------------------------------------
    def kickoff(self) -> int:
        """Open the period for every client and send the first reminder. Returns messages sent."""
        period, sent = self.period(), 0
        for client in self.store.clients():
            self.store.open_period(client["code"], period)
            if self.store.outstanding(client["code"], period) and self.store.nudges_sent(client["code"], period) == 0:
                self._nudge(client, period)
                sent += 1
        return sent

    def advance_day(self) -> int:
        self.store.today = self.store.today + timedelta(days=1)
        return self.run_followups()

    def run_followups(self) -> int:
        period, today, sent = self.period(), self.store.today, 0
        for client in self.store.clients():
            code = client["code"]
            followup = self.store.pending_followup(code)
            if not followup or date.fromisoformat(followup["due"]) > today:
                continue
            if not self.store.outstanding(code, period):
                self.store.close_followups(code)
                continue
            if today > self.deadline(period) and not any("en retard" in f["reason"] for f in self.store.flags(code)):
                missing = ", ".join(DOC_LABELS[d] for d in self.store.outstanding(code, period))
                self.store.add_flag(code, f"Dossier {period} en retard, manque : {missing}")
            self._nudge(client, period)
            sent += 1
        return sent

    def _nudge(self, client: dict, period: str) -> None:
        code = client["code"]
        count = self.store.nudges_sent(code, period)
        deadline = self.deadline(period)
        level = count
        if (deadline - self.store.today).days <= 2:
            level = templates.MAX_LEVEL
        text = templates.render(
            level, client["language"], contact=client["contact"], firm=self.firm, period=period,
            docs=self.store.outstanding(code, period), deadline=deadline.strftime("%d/%m"),
        )
        self.store.add_message(code, "out", "template", text, period=period)
        self.send(client, text)
        gap = NUDGE_GAP_DAYS[min(count, len(NUDGE_GAP_DAYS) - 1)]
        self.store.schedule_followup(code, self.store.today + timedelta(days=gap), f"relance automatique n°{count + 1}")

    # --- inbound -----------------------------------------------------------
    def receive(self, code: str, text: str = "", files: list[tuple[str, str, bytes]] = ()) -> str:
        """A client wrote. `files` is a list of (name, mime, bytes). Returns the reply sent (may be empty)."""
        self.store.client(code)  # raises KeyError for an unknown client
        period = self.period()
        self.store.open_period(code, period)
        new_ids = []
        for name, mime, data in files:
            if mime not in ALLOWED_MIME:
                raise ValueError(f"type de fichier non supporté : {mime}")
            if len(data) > MAX_FILE_BYTES:
                raise ValueError("fichier trop lourd (10 Mo max)")
            file_id = self._save_file(code, period, name, mime, data)
            new_ids.append(self.store.add_message(code, "in", "file", name, file_id=file_id))
        if text.strip():
            new_ids.append(self.store.add_message(code, "in", "text", text.strip()))
        if not new_ids:
            return ""

        reply = self.assistant.handle(code, period, new_ids)
        if reply:
            self.store.add_message(code, "out", "text", reply)
            self.send(self.store.client(code), reply)
        # Safety net: never leave an incomplete file without a next reminder.
        if self.store.outstanding(code, period) and not self.store.pending_followup(code):
            self.store.schedule_followup(code, self.store.today + timedelta(days=2), "relance après réponse du client")
        return reply

    def _save_file(self, code: str, period: str, name: str, mime: str, data: bytes) -> int:
        safe = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(name).name)[:80] or "fichier"
        folder = self.files_dir / code / period
        folder.mkdir(parents=True, exist_ok=True)
        file_id = self.store.add_file(code, period, safe, mime, "")
        path = folder / f"{file_id}_{safe}"
        path.write_bytes(data)
        self.store.db.execute("UPDATE files SET path = ? WHERE id = ?", (str(path), file_id))
        self.store.db.commit()
        return file_id

    # --- owner view --------------------------------------------------------
    def report(self) -> dict:
        period = self.period()
        rows = []
        for client in self.store.clients():
            code = client["code"]
            self.store.open_period(code, period)
            checklist = self.store.checklist(code, period)
            outstanding = [r["doc_type"] for r in checklist if r["status"] in ("missing", "partial")]
            followup = self.store.pending_followup(code)
            rows.append({
                "code": code,
                "name": client["name"],
                "contact": client["contact"],
                "language": client["language"],
                "checklist": checklist,
                "complete": not outstanding,
                "followup": followup and {"due": followup["due"], "reason": followup["reason"]},
                "nudges": self.store.nudges_sent(code, period),
                "flags": self.store.flags(code),
                "files": len(self.store.files(code, period)),
            })
        complete = sum(r["complete"] for r in rows)
        return {
            "firm": self.firm,
            "today": self.store.today.isoformat(),
            "period": period,
            "period_label": templates.month_label(period),
            "deadline": self.deadline(period).isoformat(),
            "clients": rows,
            "totals": {
                "clients": len(rows),
                "complete": complete,
                "incomplete": len(rows) - complete,
                "flags": len(self.store.flags()),
                "messages_sent": self.store.db.execute(
                    "SELECT COUNT(*) FROM messages WHERE direction = 'out'").fetchone()[0],
                "ai_cost_usd": round(self.store.total_cost_usd(), 4),
            },
        }
