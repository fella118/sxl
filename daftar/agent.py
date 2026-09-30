"""The WhatsApp assistant: reads a client's reply (text, photos, PDFs) and updates the checklist.

It never reads amounts or does accounting. Its whole job is: understand what the
client sent or promised, tick the checklist, schedule the next follow-up, answer
briefly in the client's own language, and hand anything else to a human.
"""

import base64
from datetime import date, timedelta
from pathlib import Path

from .store import CHECK_STATUSES, DOC_LABELS, DOC_TYPES, Store

MODEL = "claude-opus-5-5"
MAX_TOOL_ROUNDS = 8
# USD per million tokens for claude-opus-5-5 (cache write = 1.25x input for the 5-minute TTL).
PRICE_IN, PRICE_OUT, PRICE_CACHE_READ, PRICE_CACHE_WRITE = 4.00, 20.00, 0.20, 5.00

SYSTEM_PROMPT = """You are the WhatsApp assistant of {firm}, a Moroccan fiduciaire (accounting firm). \
You talk to the firm's clients — small business owners — for one purpose: getting their monthly \
accounting documents in on time.

The documents a client may owe for a period:
{doc_types}

How you work:
- Read what the client sent. For every photo or PDF, decide which document type it is and whether \
it belongs to the requested period, then record it with update_checklist (pass its file id). Use \
"partial" when only part of a document type arrived (e.g. 2 of 3 bank statement pages, or the \
client says more invoices are coming), "received" when it is complete, "not_applicable" only when \
the client clearly says there is nothing for that period (e.g. no sales, no employees).
- A file that is unreadable, cropped, or from the wrong month is not received: ask for a better \
photo or the right month, and do not tick it.
- When the client promises a date ("ghda", "demain", "lundi", "after Eid"), call schedule_followup \
for the day after that promise. If they give no date and documents are still missing, schedule a \
follow-up in 2 days.
- Call flag_for_accountant for anything that is not document collection: tax or accounting \
questions, fees or invoices from the firm, complaints, anger, a request to talk to the accountant, \
or anything you are unsure about. Tell the client the accountant will get back to them. Never \
answer tax, legal or accounting questions yourself, and never mention amounts.
- Then write your reply to the client as your final message. Keep it short, warm and WhatsApp-like \
(1–3 sentences). Mirror the client's language and script: Darija in Latin letters (Arabizi) if \
they write that way, Darija in Arabic script, French, or a mix — exactly as they do. Address them \
the way the firm does (e.g. "Si Ahmed", "Lalla Fatima"). Say what you received and what is still \
missing. Do not use Markdown.
- Never claim a document was received unless you recorded it."""

TOOLS = [
    {
        "name": "update_checklist",
        "description": "Record the status of one document type for the current period, and link the files that support it.",
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "doc_type": {"type": "string", "enum": DOC_TYPES},
                "status": {"type": "string", "enum": CHECK_STATUSES},
                "file_ids": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "Ids of the files that belong to this document type (may be empty).",
                },
                "note": {
                    "type": "string",
                    "description": "Short note for the accountant, in French (e.g. 'pages 1-2 sur 3', 'pas de ventes ce mois').",
                },
            },
            "required": ["doc_type", "status", "file_ids", "note"],
            "additionalProperties": False,
        },
    },
    {
        "name": "schedule_followup",
        "description": "Schedule the next reminder to this client. Replaces any previously scheduled follow-up.",
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "date": {"type": "string", "description": "YYYY-MM-DD, after today."},
                "reason": {"type": "string", "description": "Why, in French (e.g. 'a promis le relevé pour lundi')."},
            },
            "required": ["date", "reason"],
            "additionalProperties": False,
        },
    },
    {
        "name": "flag_for_accountant",
        "description": "Hand something to a human at the firm: questions, complaints, fees, anything that is not document collection.",
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {"reason": {"type": "string", "description": "What the accountant needs to handle, in French."}},
            "required": ["reason"],
            "additionalProperties": False,
        },
    },
]


class ToolError(Exception):
    pass


class Assistant:
    def __init__(self, store: Store, llm, firm: str, deadline_day: int):
        self.store = store
        self.llm = llm  # an anthropic.Anthropic() client, or a test double with the same shape
        self.firm = firm
        self.deadline_day = deadline_day
        doc_types = "\n".join(f"- {key}: {label}" for key, label in DOC_LABELS.items())
        self.system = SYSTEM_PROMPT.format(firm=firm, doc_types=doc_types)

    # --- public ----------------------------------------------------------
    def handle(self, code: str, period: str, new_message_ids: list[int]) -> str:
        """Process the client's new messages and return the reply to send (may be empty)."""
        messages = [{"role": "user", "content": self._context(code, period, new_message_ids)}]
        for _ in range(MAX_TOOL_ROUNDS):
            response = self.llm.beta.messages.create(
                model=MODEL,
                max_tokens=16000,
                system=self.system,
                tools=TOOLS,
                messages=messages,
                thinking={"type": "adaptive"},
                output_config={"effort": "medium"},
                cache_control={"type": "ephemeral"},
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
            )
            self._record_usage(code, response.usage)

            if response.stop_reason == "refusal":
                self.store.add_flag(code, "L'assistant n'a pas pu traiter ce message : à lire par un humain.")
                return ""
            if response.stop_reason == "pause_turn":
                messages.append({"role": "assistant", "content": response.content})
                continue
            if response.stop_reason != "tool_use":
                return "".join(b.text for b in response.content if b.type == "text").strip()

            messages.append({"role": "assistant", "content": response.content})
            results = []
            for block in response.content:
                if block.type != "tool_use":
                    continue
                try:
                    output, is_error = self._run_tool(code, period, block.name, block.input), False
                except (ToolError, KeyError, ValueError) as exc:
                    output, is_error = str(exc), True
                results.append({"type": "tool_result", "tool_use_id": block.id, "content": output, "is_error": is_error})
            messages.append({"role": "user", "content": results})

        self.store.add_flag(code, "Conversation trop longue pour l'assistant : à reprendre par un humain.")
        return ""

    # --- tools -----------------------------------------------------------
    def _run_tool(self, code: str, period: str, name: str, args: dict) -> str:
        if name == "update_checklist":
            for file_id in args["file_ids"]:
                self.store.tag_file(file_id, code, args["doc_type"])
            self.store.update_checklist(code, period, args["doc_type"], args["status"], args["note"])
            if not self.store.outstanding(code, period):
                self.store.close_followups(code)
                return "Enregistré. Le dossier du mois est maintenant complet."
            missing = ", ".join(self.store.outstanding(code, period))
            return f"Enregistré. Encore attendu : {missing}."
        if name == "schedule_followup":
            try:
                due = date.fromisoformat(args["date"])
            except ValueError:
                raise ToolError("date must be YYYY-MM-DD")
            today = self.store.today
            if not today < due <= today + timedelta(days=30):
                raise ToolError(f"date must be between {today + timedelta(days=1)} and {today + timedelta(days=30)}")
            self.store.schedule_followup(code, due, args["reason"])
            return f"Relance programmée le {due.isoformat()}."
        if name == "flag_for_accountant":
            self.store.add_flag(code, args["reason"])
            return "Transmis au comptable."
        raise ToolError(f"unknown tool {name}")

    # --- prompt building -------------------------------------------------
    def _context(self, code: str, period: str, new_ids: list[int]) -> list[dict]:
        client = self.store.client(code)
        today = self.store.today
        year, month = (int(x) for x in period.split("-"))
        deadline = _deadline(year, month, self.deadline_day)
        checklist = "\n".join(
            f"- {r['doc_type']}: {r['status']}" + (f" ({r['note']})" if r["note"] else "")
            for r in self.store.checklist(code, period)
        )
        followup = self.store.pending_followup(code)
        history = [m for m in self.store.messages(code, limit=30) if m["id"] not in new_ids]
        transcript = "\n".join(_line(m) for m in history) or "(no previous messages)"

        blocks: list[dict] = [{
            "type": "text",
            "text": (
                f"Today: {today.isoformat()} ({today.strftime('%A')})\n"
                f"Client: {client['name']} — contact: {client['contact']} — usual language: {client['language']}\n"
                f"Period being collected: {period} — deadline to receive documents: {deadline.isoformat()}\n"
                f"Checklist:\n{checklist}\n"
                f"Scheduled follow-up: {followup['due'] + ' — ' + followup['reason'] if followup else 'none'}\n\n"
                f"Conversation so far:\n{transcript}\n\n"
                "New message(s) from the client:"
            ),
        }]
        for m in self.store.messages(code, limit=30):
            if m["id"] not in new_ids:
                continue
            if m["file_id"]:
                f = self.store.file(m["file_id"])
                blocks.append({"type": "text", "text": f"[file id {f['id']}: {f['name']}]"})
                blocks.append(_file_block(f))
            else:
                blocks.append({"type": "text", "text": m["body"]})
        return blocks

    def _record_usage(self, code: str, usage) -> None:
        cache_read = getattr(usage, "cache_read_input_tokens", 0) or 0
        cache_write = getattr(usage, "cache_creation_input_tokens", 0) or 0
        cost = (usage.input_tokens * PRICE_IN + usage.output_tokens * PRICE_OUT
                + cache_read * PRICE_CACHE_READ + cache_write * PRICE_CACHE_WRITE) / 1_000_000
        self.store.record_usage(code, usage.input_tokens, usage.output_tokens, cache_read, cache_write, cost)


def _deadline(year: int, month: int, day: int) -> date:
    """Documents for a period are due on `day` of the following month."""
    return date(year + month // 12, month % 12 + 1, day)


def _line(m: dict) -> str:
    who = "Client" if m["direction"] == "in" else "Firm"
    body = f"[sent a file: {m['body']}]" if m["kind"] == "file" else m["body"]
    return f"{m['day']} {who}: {body}"


def _file_block(f: dict) -> dict:
    data = base64.standard_b64encode(Path(f["path"]).read_bytes()).decode()
    if f["mime"] == "application/pdf":
        return {"type": "document", "source": {"type": "base64", "media_type": "application/pdf", "data": data}}
    return {"type": "image", "source": {"type": "base64", "media_type": f["mime"], "data": data}}
