"""The SOGIXEL AI employee: one always-on service.

- Setter (24/7): GHL calls /webhooks/ghl when a prospect replies; Claude answers in seconds, books the call with
  Saad, or hands over. It only answers conversations SOGIXEL started, and never sends a first message.
- Hunter (07:30): prospector `daily`, then Claude polishes each message. `pull` on the 1st of the month.
- Follow-ups (hourly): email relances at J+3 / J+7 for approved emails without a reply; DM relances go to the cockpit.
- Reporter (18:00): the day's numbers to Saad on WhatsApp.
- Cockpit (/cockpit): Saad's phone page to send today's DMs by hand and approve emails.

Env: ANTHROPIC_API_KEY, GHL_TOKEN, GHL_LOCATION_ID, GHL_CALENDAR_ID, GHL_OWNER_CONTACT_ID, EMPLOYEE_KEY,
     PUBLIC_URL, GOOGLE_PLACES_API_KEY, META_ADLIB_TOKEN.
"""
import datetime as dt
import hmac
import json
import os
import queue
import re
import threading
import time
import traceback
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from zoneinfo import ZoneInfo

from . import outreach, store
from .ghl import GHL, GHLError
from .scoring import norm

DAYS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
_STOP = re.compile(r"\b(stop|unsubscribe|desinscri\w*|ne plus me contacter|ne m'?ecrivez plus|arretez|baraka)\b")
CHANNELS = {"instagram": "instagram", "whatsapp": "whatsapp", "email": "email", "facebook": "facebook", "sms": "sms"}
FOLLOWUP = ["Je me permets de revenir vers vous au sujet de mon message. Est-ce que remplir l'agenda de {name} est un "
            "sujet en ce moment ?",
            "Dernier message de ma part : si un jour vous voulez voir comment on répond aux demandes de vos patients en "
            "quelques secondes, même le soir, je reste disponible."]


def log(*a):
    print(dt.datetime.now().strftime("%H:%M:%S"), *a, flush=True)


def is_stop(text):
    return bool(_STOP.search(norm(text)))


def fr_label(iso, tz):
    t = dt.datetime.fromisoformat(iso).astimezone(tz)
    return f"{DAYS[t.weekday()]} {t.day} {outreach.MONTHS[t.month - 1]} à {t.hour}h{t.minute:02d}".replace("h00", "h")


def channel_of(msg_type):
    t = (msg_type or "").lower()
    return next((v for k, v in CHANNELS.items() if k in t), "instagram")


class SetterTools:
    """What Claude may do during one conversation. Side effects are recorded for the caller."""

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
    def __init__(self, cfg, master_path, out_dir, ghl=None, brain=None, now=None):
        self.cfg, self.e = cfg, cfg["employee"]
        self.tz = ZoneInfo(self.e["timezone"])
        self.master_path, self.out_dir = master_path, out_dir
        self.ghl = ghl or GHL()
        self._brain = brain
        self.now = now or (lambda: dt.datetime.now(self.tz))
        self.calendar_id = os.environ.get("GHL_CALENDAR_ID", "")
        self.owner_id = os.environ.get("GHL_OWNER_CONTACT_ID", "")
        self.lock = threading.RLock()
        self.state_path = os.path.join(os.path.dirname(master_path) or ".", "employee_state.json")
        try:
            with open(self.state_path, encoding="utf-8") as f:
                self.state = json.load(f)
        except (OSError, json.JSONDecodeError):
            self.state = {}
        self.state.setdefault("jobs", {}); self.state.setdefault("handled", {}); self.state.setdefault("day", {})

    @property
    def brain(self):
        if self._brain is None:
            from .brain import Brain
            self._brain = Brain(model=self.e["model"], setter_effort=self.e["setter_effort"],
                                polish_effort=self.e["polish_effort"], proof=self.e.get("proof", []))
        return self._brain

    def _save_state(self):
        with self.lock:
            tmp = self.state_path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.state, f, ensure_ascii=False, indent=1)
            os.replace(tmp, self.state_path)

    def _count(self, key):
        today = self.now().date().isoformat()
        if self.state["day"].get("date") != today:
            self.state["day"] = {"date": today}
        self.state["day"][key] = self.state["day"].get(key, 0) + 1

    def notify(self, text):
        log("notify:", text)
        if self.owner_id:
            try:
                self.ghl.send(self.owner_id, self.e["owner_channel"], text)
            except GHLError as ex:
                log("notify failed:", ex)

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
        def match(r):
            return r.get("ghl_contact_id") == contact_id
        with self.lock:
            rows = store.load(self.master_path)
            row = next((r for r in rows.values() if match(r)), None)
            if row and (status == "do_not_contact" or store.PROGRESS.index(status) > store.PROGRESS.index(row["status"])):
                row["status"] = status
                if note:
                    row["notes"] = f"{self.now().date()}: {note}"[:200]
                store.save(self.master_path, sorted(rows.values(), key=lambda r: -int(r.get("score") or 0)))
        if status == "do_not_contact":
            try:
                self.ghl.add_tags(contact_id, ["stop"])
            except GHLError as ex:
                log("tag failed:", ex)

    # --- setter ---------------------------------------------------------------------------------------------
    def handle_inbound(self, contact_id):
        history = self.ghl.history(contact_id)
        inbound = [m for m in history if m["direction"] == "inbound"]
        if not inbound:
            return "no_inbound"
        last = inbound[-1]
        if history[-1]["direction"] != "inbound" or self.state["handled"].get(contact_id) == last["id"]:
            return "already_answered"
        contact = self.ghl.contact(contact_id)
        ours = any(m["direction"] == "outbound" and norm(m["body"]).startswith(norm(self.e["first_touch"])) for m in history)
        if not ours and self.e["prospect_tag"] not in (contact.get("tags") or []):
            return "not_a_prospect"            # a client, a friend, a supplier: never answered by the bot
        name = contact.get("companyName") or contact.get("name") or "Prospect"
        channel = channel_of(last["type"])
        row = self._row_for(contact_id, contact)
        self.state["handled"][contact_id] = last["id"]
        self._count("replies")

        if is_stop(last["body"]):              # opt-out never waits for a model
            self.close(contact_id, "do_not_contact", note="stop")
            self.ghl.send(contact_id, channel, "C'est noté, nous ne vous écrirons plus. Bonne journée.")
            self._save_state()
            return "stopped"

        tools = SetterTools(self, contact_id, name)
        d = self.brain.answer(self._context(name, channel, row, history), tools)
        if d.get("escalate"):
            self.notify(f"{name} a écrit : « {last['body'][:200]} » — à toi de répondre ({d['escalate']}).")
        elif d["send"] and d["reply"]:
            time.sleep(self.e["reply_delay_s"])
            self.ghl.send(contact_id, channel, d["reply"], subject="Re: votre message")
        if tools.booked:
            self.close(contact_id, "call_booked")
            self._count("booked")
            self.notify(f"📅 Appel réservé : {name}, {tools.offered[tools.booked]}.")
        elif not tools.stopped:
            self.close(contact_id, "replied")
            if d.get("intent") == "interested":
                self.notify(f"🔥 {name} est intéressé : « {last['body'][:160]} »")
        self._save_state()
        return d.get("intent", "handover")

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
        hm, jobs, done = now.strftime("%H:%M"), [], self.state["jobs"]
        if hm >= self.e["daily_at"] and done.get("daily") != now.date().isoformat():
            jobs.append(("daily", now.date().isoformat()))
        if hm >= self.e["report_at"] and done.get("report") != now.date().isoformat():
            jobs.append(("report", now.date().isoformat()))
        if now.day == self.e["pull_day"] and hm >= "03:00" and done.get("pull") != now.strftime("%Y-%m"):
            jobs.append(("pull", now.strftime("%Y-%m")))
        if done.get("followups") != now.strftime("%Y-%m-%dT%H"):
            jobs.append(("followups", now.strftime("%Y-%m-%dT%H")))
        return jobs

    def run_job(self, name, key):
        try:
            getattr(self, "job_" + name)()
        except (Exception, SystemExit):            # `daily` exits when the master list is still empty
            log(f"job {name} failed:\n{traceback.format_exc()}")
            if name != "followups":
                self.notify(f"⚠️ La tâche « {name} » a échoué, voir les logs.")
        self.state["jobs"][name] = key
        self._save_state()

    def _cli(self, *argv):
        from . import __main__ as cli
        cli.main([*argv, "--master", self.master_path, "--out", self.out_dir])

    def job_pull(self):
        self._cli("pull")

    def job_daily(self):
        day = self.now().date().isoformat()
        with self.lock:
            self._cli("daily", "--date", day)
            path = os.path.join(self.out_dir, day, "queue.csv")
            rows = list(store.load(path).values())
            for r in rows:
                r["dm"], r["email_body"] = self.brain.polish(r["facts"], r["dm"], r["email_body"])
            store.save(path, rows, store.QUEUE_COLS)
        n = {c: sum(r["channel"] == c for r in rows) for c in ("dm", "email", "call")}
        self.notify(f"☀️ Liste du jour prête : {n['dm']} DM, {n['email']} emails, {n['call']} appels. "
                    f"{os.environ.get('PUBLIC_URL', '')}/cockpit?key={os.environ.get('EMPLOYEE_KEY', '')}")

    def job_report(self):
        rows = store.load(self.master_path).values()
        today = self.now().date().isoformat()
        sent = sum(1 for r in rows if r.get("sent_at", "").startswith(today))
        d = self.state["day"] if self.state["day"].get("date") == today else {}
        total = {s: sum(1 for r in rows if r["status"] == s) for s in ("sent", "replied", "call_booked", "client")}
        self.notify(f"📊 Bilan du {today} : {sent} contactés aujourd'hui, {d.get('replies', 0)} réponses traitées, "
                    f"{d.get('booked', 0)} appels réservés. Pipeline : {total['sent']} en attente, {total['replied']} en "
                    f"discussion, {total['call_booked']} appels, {total['client']} clients.")

    def job_followups(self):
        """Email relances only; DM relances are listed in the cockpit for Saad."""
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

    # --- cockpit actions ------------------------------------------------------------------------------------
    def today_queue(self):
        day = self.now().date().isoformat()
        rows = sorted(store.load(os.path.join(self.out_dir, day, "queue.csv")).values(), key=lambda r: int(r["rank"]))
        master = store.load(self.master_path)
        for r in rows:
            r["status"] = master.get(r["place_id"], {}).get("status", r["status"])
        due = [r for r in master.values() if r["status"] == "sent" and r.get("sent_channel") == "dm"
               and r.get("sent_at") and (self.now().date() - dt.date.fromisoformat(r["sent_at"][:10])).days >= 3
               and not r.get("followups")]
        return {"date": day, "queue": rows, "dm_followups": due}

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
def make_handler(emp, inbox):
    key = os.environ.get("EMPLOYEE_KEY", "")
    cockpit = os.path.join(os.path.dirname(__file__), "cockpit.html")

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _authed(self):
            q = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
            given = self.headers.get("X-Employee-Key") or (q.get("key") or [""])[0]
            return bool(key) and hmac.compare_digest(given, key)

        def _send(self, code, body, ctype="application/json"):
            data = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode()
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _body(self):
            n = int(self.headers.get("Content-Length") or 0)
            try:
                return json.loads(self.rfile.read(n) or b"{}")
            except json.JSONDecodeError:
                return {}

        def do_GET(self):
            path = urllib.parse.urlsplit(self.path).path
            if path == "/health":
                return self._send(200, {"ok": True})
            if not self._authed():
                return self._send(403, {"error": "forbidden"})
            if path == "/cockpit":
                with open(cockpit, "rb") as f:
                    return self._send(200, f.read(), "text/html; charset=utf-8")
            if path == "/api/today":
                return self._send(200, emp.today_queue())
            return self._send(404, {"error": "not found"})

        def do_POST(self):
            path = urllib.parse.urlsplit(self.path).path
            if not self._authed():
                return self._send(403, {"error": "forbidden"})
            body = self._body()
            if path == "/webhooks/ghl":
                cid = body.get("contact_id") or body.get("contactId") or (body.get("contact") or {}).get("id")
                if not cid:
                    return self._send(400, {"error": "contact_id missing"})
                inbox.put(cid)
                return self._send(200, {"queued": True})
            if path == "/api/status":
                return self._send(200, {"ok": emp.mark(body.get("place_id", ""), body.get("status", ""))})
            if path == "/api/approve_email":
                try:
                    return self._send(200, {"ok": emp.approve_email(body.get("place_id", ""))})
                except GHLError as ex:
                    return self._send(502, {"ok": False, "error": str(ex)[:200]})
            return self._send(404, {"error": "not found"})

    return Handler


def _setter_loop(emp, inbox):
    while True:
        cid = inbox.get()
        try:
            log(f"inbound {cid}: {emp.handle_inbound(cid)}")
        except Exception:
            log(f"inbound {cid} failed:\n{traceback.format_exc()}")
            emp.notify(f"⚠️ Je n'ai pas pu répondre à un prospect (contact {cid}). Regarde la conversation dans GHL.")


def _scheduler_loop(emp, stop):
    while not stop.wait(30):
        for name, k in emp.due_jobs():
            log("job", name)
            emp.run_job(name, k)


def serve(cfg, master_path, out_dir, port=None):
    if not os.environ.get("EMPLOYEE_KEY"):
        raise SystemExit("EMPLOYEE_KEY is not set: it protects the webhook and the cockpit.")
    emp, inbox, stop = Employee(cfg, master_path, out_dir), queue.Queue(), threading.Event()
    threading.Thread(target=_setter_loop, args=(emp, inbox), daemon=True).start()
    threading.Thread(target=_scheduler_loop, args=(emp, stop), daemon=True).start()
    port = int(port or os.environ.get("PORT", 8080))
    log(f"SOGIXEL employee on :{port}")
    ThreadingHTTPServer(("0.0.0.0", port), make_handler(emp, inbox)).serve_forever()
