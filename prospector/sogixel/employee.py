"""The SOGIXEL AI employee: one always-on service.

- Setter (24/7): GHL calls /webhooks/ghl when a prospect replies; the event is stored, then Claude answers within
  seconds, books the call with Saad, or hands over. It only answers conversations SOGIXEL started.
- Hunter (07:30): prospector `daily`, then Claude polishes each message. `pull` on the 1st of the month.
- Follow-ups (hourly): email relances at J+3 / J+7 for approved emails without a reply; DM relances go to the cockpit.
- Reporter (18:00): the day's numbers to Saad. Backup (02:30): master list + runtime database, 14 days kept.
- Cockpit (/cockpit): Saad's phone page to send today's DMs by hand and approve emails.

SETTER_MODE=shadow (default) sends every reply to Saad as a draft instead of to the prospect; `live` sends it.
Env: see .env.example.
"""
import datetime as dt
import glob
import hmac
import json
import os
import re
import shutil
import threading
import time
import traceback
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from zoneinfo import ZoneInfo

from . import outreach, store
from .ghl import GHL, GHLError
from .ops import Ops
from .scoring import norm

DAYS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
_STOP = re.compile(r"\b(stop|unsubscribe|desinscri\w*|ne plus me contacter|ne m'?ecrivez plus|arretez|baraka)\b")
CHANNELS = {"instagram": "instagram", "whatsapp": "whatsapp", "email": "email", "facebook": "facebook", "sms": "sms"}
FOLLOWUP = ["Je me permets de revenir vers vous au sujet de mon message. Est-ce que remplir l'agenda de {name} est un "
            "sujet en ce moment ?",
            "Dernier message de ma part : si un jour vous voulez voir comment on répond aux demandes de vos patients en "
            "quelques secondes, même le soir, je reste disponible."]
STOP_REPLY = "C'est noté, nous ne vous écrirons plus. Bonne journée."
PAUSE_TAG = "bot-pause"           # Saad adds this tag in GHL to take a conversation over
MAX_BODY = 64 * 1024


def log(event, **fields):
    """One JSON line per event: easy to grep, easy to ship to any log tool."""
    print(json.dumps({"ts": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "event": event, **fields},
                     ensure_ascii=False, default=str), flush=True)


def is_stop(text):
    return bool(_STOP.search(norm(text)))


def fr_label(iso, tz):
    t = dt.datetime.fromisoformat(iso).astimezone(tz)
    return f"{DAYS[t.weekday()]} {t.day} {outreach.MONTHS[t.month - 1]} à {t.hour}h{t.minute:02d}".replace("h00", "h")


def channel_of(msg_type):
    t = (msg_type or "").lower()
    return next((v for k, v in CHANNELS.items() if k in t), "instagram")


def _when(msg):
    try:
        t = dt.datetime.fromisoformat(msg["date"].replace("Z", "+00:00"))
    except (KeyError, ValueError, AttributeError):
        return None
    return t if t.tzinfo else t.replace(tzinfo=dt.timezone.utc)


def cockpit_key():
    return os.environ.get("COCKPIT_KEY") or os.environ.get("EMPLOYEE_KEY", "")


def webhook_key():
    return os.environ.get("WEBHOOK_KEY") or os.environ.get("EMPLOYEE_KEY", "")


class SetterTools:
    """What Claude may do during one conversation. In shadow mode nothing is booked."""

    def __init__(self, emp, contact_id, name):
        self.emp, self.contact_id, self.name = emp, contact_id, name
        self.offered, self.booked, self.escalated, self.stopped = {}, None, None, False

    def run(self, name, args):
        return getattr(self, name)(**args)

    def get_free_slots(self, days_ahead):
        e, now = self.emp, self.emp.now()
        start, end = now + dt.timedelta(hours=2), (now + dt.timedelta(days=days_ahead)).replace(hour=23, minute=59)
        slots = e.ghl.free_slots(e.calendar_id, int(start.timestamp() * 1000), int(end.timestamp() * 1000), e.e["timezone"])
        picked, per_day = [], {}
        for s in slots:                         # two per day, office hours, up to six
            t = dt.datetime.fromisoformat(s).astimezone(e.tz)
            if 9 <= t.hour < 19 and per_day.get(t.date(), 0) < 2:
                per_day[t.date()] = per_day.get(t.date(), 0) + 1
                picked.append(s)
            if len(picked) == 6:
                break
        self.offered = {s: fr_label(s, e.tz) for s in picked}
        return [{"start_time": s, "label": label} for s, label in self.offered.items()] or {"slots": [], "note": "aucun créneau"}

    def book_call(self, start_time):
        if start_time not in self.offered:
            raise ValueError("start_time must be one of the slots returned by get_free_slots")
        if self.emp.live:
            self.emp.ghl.book(self.emp.calendar_id, self.contact_id, start_time, f"Appel SOGIXEL — {self.name}")
        self.booked = start_time
        return {"booked": True, "label": self.offered[start_time]}

    def mark_do_not_contact(self, reason):
        self.stopped = True
        self.emp.close(self.contact_id, "do_not_contact", note=reason)
        return {"ok": True}

    def escalate_to_saad(self, summary, urgency):
        self.escalated = summary
        self.emp.notify(f"{'🔴 ' if urgency == 'urgent' else ''}{self.name} : {summary}")
        return {"ok": True, "message": "Saad est prévenu"}


class Employee:
    def __init__(self, cfg, master_path, out_dir, ghl=None, brain=None, now=None, mode=None):
        self.cfg, self.e = cfg, cfg["employee"]
        self.tz = ZoneInfo(self.e["timezone"])
        self.master_path, self.out_dir = master_path, out_dir
        self.data_dir = os.path.dirname(master_path) or "."
        self.ghl = ghl or GHL()
        self._brain = brain
        self.now = now or (lambda: dt.datetime.now(self.tz))
        self.mode = mode or os.environ.get("SETTER_MODE", "shadow")
        self.live = self.mode == "live"
        self.calendar_id = os.environ.get("GHL_CALENDAR_ID", "")
        self.owner_id = os.environ.get("GHL_OWNER_CONTACT_ID", "")
        self.lock = threading.RLock()            # guards the CSV master list
        self.ops = Ops(os.path.join(self.data_dir, "employee.db"))
        self.wake = threading.Event()

    @property
    def brain(self):
        if self._brain is None:
            from .brain import Brain
            self._brain = Brain(model=self.e["model"], setter_effort=self.e["setter_effort"],
                                polish_effort=self.e["polish_effort"], proof=self.e.get("proof", []))
        return self._brain

    def today(self):
        return self.now().date().isoformat()

    def notify(self, text):
        log("notify", text=text)
        if self.owner_id:
            try:
                self.ghl.send(self.owner_id, self.e["owner_channel"], text)
            except GHLError as ex:
                log("notify_failed", error=str(ex))

    def notify_once(self, key, text):
        """At most one such notification per day."""
        if not self.ops.count(self.today(), "notified:" + key):
            self.ops.bump(self.today(), "notified:" + key)
            self.notify(text)

    def send_to_prospect(self, contact_id, channel, text):
        resp = self.ghl.send(contact_id, channel, text, subject="Re: votre message") or {}
        self.ops.record_sent(contact_id, resp.get("messageId") or resp.get("emailMessageId") or "", text)

    # --- master list ----------------------------------------------------------------------------------------
    def _update_master(self, match, **fields):
        """Update the first master row for which match(row) is true. Returns the row or None."""
        with self.lock:
            rows = store.load(self.master_path)
            row = next((r for r in rows.values() if match(r)), None)
            if row:
                row.update(fields)
                store.save(self.master_path, sorted(rows.values(), key=lambda r: -int(r.get("score") or 0)))
            return row

    def _row_for(self, contact_id, contact):
        handle = norm(contact.get("name") or contact.get("firstName") or "").replace(" ", "")
        email = (contact.get("email") or "").lower()

        def match(r):
            return (r.get("ghl_contact_id") == contact_id or (email and r.get("email_generic") == email)
                    or (handle and r.get("ig_handle") and norm(r["ig_handle"]).replace(".", "") in handle.replace(".", "")))
        return self._update_master(match, ghl_contact_id=contact_id)

    def close(self, contact_id, status, note=""):
        """Move this contact's prospect forward (never backward, except `do_not_contact` which always wins)."""
        with self.lock:
            rows = store.load(self.master_path)
            row = next((r for r in rows.values() if r.get("ghl_contact_id") == contact_id), None)
            if row and (status == "do_not_contact" or store.PROGRESS.index(status) > store.PROGRESS.index(row["status"])):
                row["status"] = status
                if note:
                    row["notes"] = f"{self.today()}: {note}"[:200]
                store.save(self.master_path, sorted(rows.values(), key=lambda r: -int(r.get("score") or 0)))
        if status == "do_not_contact":
            try:
                self.ghl.add_tags(contact_id, ["stop"])
            except GHLError as ex:
                log("tag_failed", error=str(ex))

    # --- setter ---------------------------------------------------------------------------------------------
    def handle_inbound(self, contact_id):
        history = self.ghl.history(contact_id)
        inbound = [m for m in history if m["direction"] == "inbound"]
        if not inbound:
            return "no_inbound"
        last = inbound[-1]
        if history[-1]["direction"] != "inbound" or self.ops.handled(contact_id) == last["id"]:
            return "already_answered"
        contact = self.ghl.contact(contact_id)
        tags = contact.get("tags") or []
        ours = any(m["direction"] == "outbound" and norm(m["body"]).startswith(norm(self.e["first_touch"])) for m in history)
        if not ours and self.e["prospect_tag"] not in tags:
            return "not_a_prospect"            # a client, a friend, a supplier: never answered by the bot
        name = contact.get("companyName") or contact.get("name") or "Prospect"
        if PAUSE_TAG in tags or self.ops.paused(contact_id):
            return "paused"
        if self._human_took_over(contact_id, history):
            self.ops.pause(contact_id, "Saad a répondu lui-même")
            return "human_takeover"

        channel, day = channel_of(last["type"]), self.today()
        row = self._row_for(contact_id, contact)
        self.ops.set_handled(contact_id, last["id"])
        self.ops.bump(day, "replies")

        if is_stop(last["body"]):              # opt-out never waits for a model
            self.close(contact_id, "do_not_contact", note="stop")
            if self.live:
                self.send_to_prospect(contact_id, channel, STOP_REPLY)
            else:
                self.notify(f"🧪 {name} a demandé stop : retiré de la liste (aucun message envoyé en mode test).")
            return "stopped"

        if self.ops.count(day, f"ai:{contact_id}") >= self.e["max_replies_per_contact_day"]:
            self.ops.pause(contact_id, "plafond d'échanges atteint")
            self.notify(f"{name} : beaucoup d'échanges aujourd'hui, je te laisse la main.")
            return "capped"
        if self.ops.count(day, "ai") >= self.e["max_ai_replies_day"]:
            self.notify_once("daily_cap", "⚠️ Plafond quotidien de réponses IA atteint : les suivantes attendent toi.")
            return "daily_cap"
        if self._looks_automatic(contact_id, history):
            return "auto_reply_suspected"      # a clinic's own auto-responder: never start a bot-to-bot loop

        self.ops.bump(day, "ai")
        self.ops.bump(day, f"ai:{contact_id}")
        tools = SetterTools(self, contact_id, name)
        d = self.brain.answer(self._context(name, channel, row, history), tools)
        if d.get("escalate"):
            self.notify(f"{name} a écrit : « {last['body'][:200]} » — à toi de répondre ({d['escalate']}).")
        elif d["send"] and d["reply"]:
            if self.live:
                time.sleep(self.e["reply_delay_s"])
                self.send_to_prospect(contact_id, channel, d["reply"])
            else:
                # a draft Saad pastes unchanged still counts as the bot's message (no false "takeover")
                self.ops.record_sent(contact_id, "", d["reply"])
                booked = f"\n(réservation simulée : {tools.offered[tools.booked]})" if tools.booked else ""
                self.notify(f"🧪 Brouillon pour {name} ({d['intent']}) :\n« {d['reply']} »{booked}")
        if tools.booked and self.live:
            self.close(contact_id, "call_booked")
            self.ops.bump(day, "booked")
            self.notify(f"📅 Appel réservé : {name}, {tools.offered[tools.booked]}.")
        elif not tools.stopped:
            self.close(contact_id, "replied")
            if d.get("intent") == "interested" and self.live:
                self.notify(f"🔥 {name} est intéressé : « {last['body'][:160]} »")
        return d.get("intent", "handover")

    def _human_took_over(self, contact_id, history):
        """An outbound message after the prospect's first reply that the bot didn't send = Saad is on it."""
        first_in = next(i for i, m in enumerate(history) if m["direction"] == "inbound")
        ids, bodies = self.ops.ours(contact_id)
        return any(m["direction"] == "outbound" and m["id"] not in ids and m["body"].strip() not in bodies
                   for m in history[first_in:])

    def _looks_automatic(self, contact_id, history):
        """The prospect 'answered' our last reply within seconds, or sent the very same text twice."""
        ids, bodies = self.ops.ours(contact_id)
        mine = [m for m in history if m["direction"] == "outbound" and (m["id"] in ids or m["body"].strip() in bodies)]
        theirs = [m for m in history if m["direction"] == "inbound"]
        if len(theirs) >= 2 and theirs[-1]["body"].strip() and theirs[-1]["body"].strip() == theirs[-2]["body"].strip():
            return True
        if mine:
            a, b = _when(mine[-1]), _when(theirs[-1])
            if a and b and dt.timedelta(0) <= b - a < dt.timedelta(seconds=self.e["autoreply_window_s"]):
                return True
        return False

    def _context(self, name, channel, row, history):
        now = self.now()
        lines = [f"Now: {DAYS[now.weekday()]} {now:%d/%m/%Y %H:%M} (Morocco time)", f"Channel: {channel}",
                 f"Prospect: {name}"]
        if row:
            lines.append(f"What we know (verified): vertical {row.get('vertical')}, city {row.get('city')}, "
                         f"findings {row.get('flags')}; ads: {row.get('ads_evidence') or 'none seen'}")
        lines.append("\nConversation, oldest first:")
        for m in history[-20:]:
            who = "SOGIXEL" if m["direction"] == "outbound" else "PROSPECT"
            lines.append(f"[{who}] {m['body'].strip()}")
        lines.append("\nWrite SOGIXEL's next reply to the prospect's last message.")
        return "\n".join(lines)

    # --- scheduled jobs -------------------------------------------------------------------------------------
    def due_jobs(self, now=None):
        now = now or self.now()
        hm, day, jobs = now.strftime("%H:%M"), now.date().isoformat(), []
        for name, at in (("backup", self.e["backup_at"]), ("daily", self.e["daily_at"]), ("report", self.e["report_at"])):
            if hm >= at and self.ops.job_key(name) != day:
                jobs.append((name, day))
        if now.day == self.e["pull_day"] and hm >= "03:00" and self.ops.job_key("pull") != now.strftime("%Y-%m"):
            jobs.append(("pull", now.strftime("%Y-%m")))
        if self.ops.job_key("followups") != now.strftime("%Y-%m-%dT%H"):
            jobs.append(("followups", now.strftime("%Y-%m-%dT%H")))
        return jobs

    def run_job(self, name, key):
        log("job_start", job=name)
        try:
            getattr(self, "job_" + name)()
            self.ops.record_job(name, key, True)
            log("job_done", job=name)
        except (Exception, SystemExit) as ex:      # `daily` exits when the master list is still empty
            self.ops.record_job(name, key, False, f"{type(ex).__name__}: {ex}")
            log("job_failed", job=name, error=traceback.format_exc())
            if name != "followups":
                self.notify(f"⚠️ La tâche « {name} » a échoué : {type(ex).__name__}. Voir les logs.")

    def _cli(self, *argv):
        from . import __main__ as cli
        cli.main([*argv, "--master", self.master_path, "--out", self.out_dir])

    def job_pull(self):
        self._cli("pull")

    def job_daily(self):
        day = self.today()
        if not store.load(self.master_path):          # fresh install: nothing to work on yet
            self.notify_once("no_master", "La liste de cliniques est vide : lance le premier pull (voir DEPLOY.md).")
            return
        with self.lock:
            self._cli("daily", "--date", day)
            path = os.path.join(self.out_dir, day, "queue.csv")
            rows = list(store.load(path).values())
            for r in rows:
                r["dm"], r["email_body"] = self.brain.polish(r["facts"], r["dm"], r["email_body"])
            store.save(path, rows, store.QUEUE_COLS)
        n = {c: sum(r["channel"] == c for r in rows) for c in ("dm", "email", "call")}
        self.notify(f"☀️ Liste du jour prête : {n['dm']} DM, {n['email']} emails, {n['call']} appels. "
                    f"{os.environ.get('PUBLIC_URL', '')}/cockpit?key={cockpit_key()}")

    def job_report(self):
        rows = store.load(self.master_path).values()
        day = self.today()
        sent = sum(1 for r in rows if (r.get("sent_at") or "").startswith(day))
        total = {s: sum(1 for r in rows if r["status"] == s) for s in ("sent", "replied", "call_booked", "client")}
        mode = "" if self.live else " (mode test : réponses envoyées à toi seulement)"
        self.notify(f"📊 Bilan du {day}{mode} : {sent} contactés, {self.ops.count(day, 'replies')} réponses reçues, "
                    f"{self.ops.count(day, 'booked')} appels réservés. Pipeline : {total['sent']} en attente, "
                    f"{total['replied']} en discussion, {total['call_booked']} appels, {total['client']} clients.")

    def job_followups(self):
        """Email relances only (live mode); DM relances are listed in the cockpit for Saad."""
        if not self.live:
            return
        today = self.now().date()
        for r in list(store.load(self.master_path).values()):
            k = int(r.get("followups") or 0)
            if (r["status"] != "sent" or r.get("sent_channel") != "email" or k >= len(self.e["followup_days"])
                    or not r.get("ghl_contact_id") or not r.get("sent_at")):
                continue
            if (today - dt.date.fromisoformat(r["sent_at"][:10])).days < self.e["followup_days"][k]:
                continue
            name = self.ghl.contact(r["ghl_contact_id"]).get("companyName") or "votre clinique"
            text = f"Bonjour,\n\n{FOLLOWUP[k].format(name=name)}\n\nSaad\nSOGIXEL\n\n{outreach.OPT_OUT}"
            self.ghl.send(r["ghl_contact_id"], "email", text, subject="Re: mon message")
            self._update_master(lambda x: x["place_id"] == r["place_id"], followups=str(k + 1))

    def job_backup(self):
        dest = os.path.join(self.data_dir, "backups", self.today())
        os.makedirs(dest, exist_ok=True)
        with self.lock:
            if os.path.exists(self.master_path):
                shutil.copy2(self.master_path, dest)
        self.ops.backup(os.path.join(dest, "employee.db"))
        for old in sorted(glob.glob(os.path.join(self.data_dir, "backups", "*")))[:-self.e["backup_keep_days"]]:
            shutil.rmtree(old, ignore_errors=True)

    # --- status, cockpit ------------------------------------------------------------------------------------
    def health(self):
        return {"ok": True, "mode": self.mode, "pending": self.ops.pending(), "jobs": self.ops.jobs(),
                "today": {k: self.ops.count(self.today(), k) for k in ("replies", "ai", "booked")}}

    def today_queue(self):
        day = self.today()
        rows = sorted(store.load(os.path.join(self.out_dir, day, "queue.csv")).values(), key=lambda r: int(r["rank"]))
        master = store.load(self.master_path)
        for r in rows:
            r["status"] = master.get(r["place_id"], {}).get("status", r["status"])
        due = [r for r in master.values() if r["status"] == "sent" and r.get("sent_channel") == "dm"
               and r.get("sent_at") and (self.now().date() - dt.date.fromisoformat(r["sent_at"][:10])).days >= 3
               and not r.get("followups")]
        return {"date": day, "mode": self.mode, "queue": rows, "dm_followups": due}

    MARKS = {"sent", "replied", "call_booked", "client", "not_interested", "do_not_contact", "dm_followed_up"}

    def mark(self, place_id, status):
        if status not in self.MARKS:
            return False
        fields = {"status": status}
        if status == "sent":
            fields.update(sent_at=self.now().isoformat(timespec="minutes"), sent_channel="dm")
        if status == "dm_followed_up":
            fields = {"followups": "1"}
        return self._update_master(lambda r: r["place_id"] == place_id, **fields) is not None

    def approve_email(self, place_id):
        q = next((r for r in self.today_queue()["queue"] if r["place_id"] == place_id and r["email"]), None)
        if not q:
            return False
        contact = self.ghl.upsert_contact(email=q["email"], companyName=q["name"], tags=[self.e["prospect_tag"]],
                                          source="SOGIXEL prospector")
        self.ghl.send(contact["id"], "email", q["email_body"], subject=q["email_subject"])
        self._update_master(lambda r: r["place_id"] == place_id, status="sent", sent_channel="email",
                            sent_at=self.now().isoformat(timespec="minutes"), ghl_contact_id=contact["id"],
                            followups="0")
        return True


# --- HTTP -----------------------------------------------------------------------------------------------------
def make_handler(emp):
    cockpit = os.path.join(os.path.dirname(__file__), "cockpit.html")

    def same(given, expected):
        return bool(expected) and bool(given) and hmac.compare_digest(given, expected)

    class Handler(BaseHTTPRequestHandler):
        server_version = "sogixel"

        def log_message(self, *a):
            pass

        def _query(self):
            return urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)

        def _cookie(self):
            for part in (self.headers.get("Cookie") or "").split(";"):
                k, _, v = part.strip().partition("=")
                if k == "sx":
                    return v
            return ""

        def _cockpit_ok(self):
            k = cockpit_key()
            return any(same(g, k) for g in (self._cookie(), self.headers.get("X-Employee-Key", ""),
                                            (self._query().get("key") or [""])[0]))

        def _send(self, code, body, ctype="application/json", headers=()):
            data = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode()
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            for k, v in headers:
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(data)

        def _body(self):
            n = int(self.headers.get("Content-Length") or 0)
            if n > MAX_BODY:
                return None
            try:
                return json.loads(self.rfile.read(n) or b"{}")
            except json.JSONDecodeError:
                return {}

        def do_GET(self):
            path = urllib.parse.urlsplit(self.path).path
            if path == "/health":
                return self._send(200, {"ok": True, "mode": emp.mode, "pending": emp.ops.pending()})
            if not self._cockpit_ok():
                return self._send(403, {"error": "forbidden"})
            if path == "/cockpit":
                if self._query().get("key"):      # first visit from the WhatsApp link: keep the key in a cookie only
                    cookie = f"sx={cockpit_key()}; Path=/; Max-Age=2592000; HttpOnly; Secure; SameSite=Strict"
                    return self._send(302, b"", "text/plain", [("Set-Cookie", cookie), ("Location", "/cockpit")])
                with open(cockpit, "rb") as f:
                    return self._send(200, f.read(), "text/html; charset=utf-8")
            if path == "/api/today":
                return self._send(200, emp.today_queue())
            if path == "/status":
                return self._send(200, emp.health())
            return self._send(404, {"error": "not found"})

        def do_POST(self):
            path = urllib.parse.urlsplit(self.path).path
            body = self._body()
            if body is None:
                return self._send(413, {"error": "too large"})
            if path == "/webhooks/ghl":
                given = self.headers.get("X-Webhook-Key") or (self._query().get("key") or [""])[0]
                if not same(given, webhook_key()):
                    return self._send(403, {"error": "forbidden"})
                # only the ID is taken from the payload: everything else is re-read from GHL
                cid = body.get("contact_id") or body.get("contactId") or (body.get("contact") or {}).get("id")
                if not cid or not isinstance(cid, str) or len(cid) > 64:
                    return self._send(400, {"error": "contact_id missing"})
                emp.ops.enqueue(cid)
                emp.wake.set()
                return self._send(200, {"queued": True})
            if not self._cockpit_ok():
                return self._send(403, {"error": "forbidden"})
            if path == "/api/status":
                return self._send(200, {"ok": emp.mark(body.get("place_id", ""), body.get("status", ""))})
            if path == "/api/approve_email":
                try:
                    return self._send(200, {"ok": emp.approve_email(body.get("place_id", ""))})
                except GHLError as ex:
                    return self._send(502, {"ok": False, "error": str(ex)[:200]})
            return self._send(404, {"error": "not found"})

    return Handler


def process_inbox(emp):
    """Handle every stored event once. Failures are retried up to 3 times, then Saad is told."""
    while (ev := emp.ops.claim()):
        try:
            result = emp.handle_inbound(ev["contact_id"])
            emp.ops.finish(ev["id"], result)
            log("inbound", contact=ev["contact_id"], result=result)
        except Exception as ex:
            status = emp.ops.finish(ev["id"], f"{type(ex).__name__}: {ex}", ok=False)
            log("inbound_failed", contact=ev["contact_id"], retry=status == "pending", error=traceback.format_exc())
            if status == "error":
                emp.notify(f"⚠️ Je n'ai pas pu répondre à un prospect (contact {ev['contact_id']}). "
                           "Regarde la conversation dans GHL.")
            else:
                time.sleep(5)


def _setter_loop(emp):
    while True:
        process_inbox(emp)
        emp.wake.wait(10)
        emp.wake.clear()


def _scheduler_loop(emp):
    while True:
        for name, k in emp.due_jobs():
            emp.run_job(name, k)
        time.sleep(30)


def serve(cfg, master_path, out_dir, port=None):
    missing = [k for k in ("ANTHROPIC_API_KEY", "GHL_TOKEN", "GHL_LOCATION_ID", "GHL_CALENDAR_ID") if not os.environ.get(k)]
    if not cockpit_key() or not webhook_key():
        missing.append("COCKPIT_KEY/WEBHOOK_KEY (or EMPLOYEE_KEY)")
    if missing:
        raise SystemExit("Missing configuration: " + ", ".join(missing) + ". Run `python -m sogixel check`.")
    emp = Employee(cfg, master_path, out_dir)
    threading.Thread(target=_setter_loop, args=(emp,), daemon=True, name="setter").start()
    threading.Thread(target=_scheduler_loop, args=(emp,), daemon=True, name="scheduler").start()
    port = int(port or os.environ.get("PORT", 8080))
    log("start", port=port, mode=emp.mode, pending=emp.ops.pending())
    ThreadingHTTPServer(("0.0.0.0", port), make_handler(emp)).serve_forever()
