"""AI employee tests: Claude and GoHighLevel are faked, nothing leaves the machine."""
import datetime as dt
import json
import os
import queue
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from types import SimpleNamespace as NS
from unittest import mock
from zoneinfo import ZoneInfo

from sogixel import __main__ as cli, brain, employee, store

CFG = cli.load_cfg(os.path.join(os.path.dirname(__file__), "..", "config.toml"))
CFG["employee"]["reply_delay_s"] = 0
TZ = ZoneInfo("Africa/Casablanca")
NOW = dt.datetime(2026, 10, 9, 21, 14, tzinfo=TZ)          # a Friday evening
SLOT = lambda d, h, m=0: dt.datetime(2026, 10, d, h, m, tzinfo=TZ).isoformat()   # whatever offset tzdata gives
FIRST = "Bonjour, je suis Saad, fondateur de SOGIXEL. J'ai vu que votre site n'a pas de pixel Meta..."


def text(t):
    return NS(type="text", text=t)


def tool(i, name, args):
    return NS(type="tool_use", id=i, name=name, input=args)


def reply(stop, *blocks):
    return NS(stop_reason=stop, content=list(blocks))


class FakeClaude:
    def __init__(self, *responses):
        self.responses, self.calls = list(responses), []
        self.beta = NS(messages=NS(create=self._create))

    def _create(self, **kw):
        self.calls.append(kw)
        return self.responses.pop(0)


class FakeGHL:
    def __init__(self, history, tags=()):
        self._history, self.tags, self.sent, self.booked, self.tagged = history, list(tags), [], [], []

    def history(self, cid):
        return self._history

    def contact(self, cid):
        return {"id": cid, "companyName": "Clinique Exemple", "tags": self.tags}

    def send(self, cid, channel, text, subject=None):
        self.sent.append((cid, channel, text))
        self._history.append({"id": f"out{len(self.sent)}", "direction": "outbound", "body": text, "type": "", "date": "z"})

    def free_slots(self, cal, start, end, tz):
        return [SLOT(12, 8), SLOT(12, 11), SLOT(12, 15), SLOT(13, 10, 30), SLOT(13, 20)]

    def book(self, cal, cid, start, title):
        self.booked.append(start)

    def add_tags(self, cid, tags):
        self.tagged += tags

    def upsert_contact(self, **f):
        return {"id": "c-email"}


def msgs(*pairs):
    return [{"id": f"m{i}", "direction": d, "body": b, "type": "TYPE_INSTAGRAM", "date": f"2026-10-0{i + 1}"}
            for i, (d, b) in enumerate(pairs)]


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.master = os.path.join(self.tmp.name, "data", "prospects.csv")
        self.out = os.path.join(self.tmp.name, "out")
        store.save(self.master, [{"place_id": "p1", "vertical": "dental", "city": "Casablanca", "score": "75",
                                  "tier": "Hot", "flags": "no_tracking", "ig_handle": "clinique.exemple",
                                  "status": "sent", "sent_channel": "dm", "sent_at": "2026-10-05T10:00"}])

    def tearDown(self):
        self.tmp.cleanup()

    def emp(self, ghl, claude=None):
        b = brain.Brain(client=claude) if claude else None
        return employee.Employee(CFG, self.master, self.out, ghl=ghl, brain=b, now=lambda: NOW)


class BrainTest(unittest.TestCase):
    def test_tool_loop_books_and_returns_decision(self):
        claude = FakeClaude(
            reply("tool_use", tool("t1", "get_free_slots", {"days_ahead": 3})),
            reply("tool_use", tool("t2", "book_call", {"start_time": "2026-10-12T11:00:00+01:00"})),
            reply("end_turn", text(json.dumps({"reply": "C'est réservé pour lundi 12 octobre à 11h.",
                                               "intent": "booked", "send": True}))))
        calls = []

        class Tools:
            def run(self, name, args):
                calls.append(name)
                return {"ok": True}

        d = brain.Brain(client=claude).answer("context", Tools())
        self.assertEqual((d["intent"], d["send"]), ("booked", True))
        self.assertEqual(calls, ["get_free_slots", "book_call"])
        first = claude.calls[0]
        self.assertEqual((first["model"], first["fallbacks"], first["betas"]),
                         ("claude-opus-5-5", "default", ["server-side-fallback-2026-07-01"]))
        self.assertEqual(first["output_config"]["format"]["type"], "json_schema")
        results = [m for m in claude.calls[-1]["messages"] if m["role"] == "user"][-1]["content"][0]
        self.assertEqual(results["tool_use_id"], "t2")         # results are sent back with the matching id

    def test_tool_error_goes_back_to_the_model(self):
        claude = FakeClaude(reply("tool_use", tool("t1", "book_call", {"start_time": "x"})),
                            reply("end_turn", text('{"reply": "Quel créneau ?", "intent": "question", "send": true}')))

        class Tools:
            def run(self, name, args):
                raise ValueError("start_time must be one of the slots")

        brain.Brain(client=claude).answer("c", Tools())
        result = [m for m in claude.calls[-1]["messages"] if m["role"] == "user"][-1]["content"][0]
        self.assertTrue(result["is_error"])

    def test_refusal_escalates(self):
        d = brain.Brain(client=FakeClaude(reply("refusal"))).answer("c", None)
        self.assertEqual((d["send"], d["escalate"]), (False, "refusal"))

    def test_polish_keeps_drafts_on_bad_output(self):
        b = brain.Brain(client=FakeClaude(reply("end_turn", text("not json"))))
        self.assertEqual(b.polish("facts", "dm", "body"), ("dm", "body"))


class SetterTest(Base):
    def test_answers_our_conversation_and_books(self):
        ghl = FakeGHL(msgs(("outbound", FIRST), ("inbound", "Intéressant. On peut en parler quand ?")))
        claude = FakeClaude(
            reply("tool_use", tool("t1", "get_free_slots", {"days_ahead": 3})),
            reply("tool_use", tool("t2", "book_call", {"start_time": SLOT(12, 11)})),
            reply("end_turn", text('{"reply": "Parfait, lundi 12 octobre à 11h.", "intent": "booked", "send": true}')))
        e = self.emp(ghl, claude)
        e._update_master(lambda r: True, ghl_contact_id="c1")
        self.assertEqual(e.handle_inbound("c1"), "booked")
        self.assertEqual(ghl.sent[0], ("c1", "instagram", "Parfait, lundi 12 octobre à 11h."))
        self.assertEqual(ghl.booked, [SLOT(12, 11)])
        self.assertEqual(store.load(self.master)["p1"]["status"], "call_booked")
        self.assertIn("PROSPECT] Intéressant", claude.calls[0]["messages"][0]["content"])

    def test_never_answers_someone_we_did_not_prospect(self):
        claude = FakeClaude()
        ghl = FakeGHL(msgs(("inbound", "Salam, c'est pour mon rendez-vous de demain")))
        self.assertEqual(self.emp(ghl, claude).handle_inbound("c9"), "not_a_prospect")
        self.assertEqual((ghl.sent, claude.calls), ([], []))

    def test_stop_is_handled_without_the_model(self):
        claude = FakeClaude()
        ghl = FakeGHL(msgs(("outbound", FIRST), ("inbound", "STOP merci")))
        e = self.emp(ghl, claude)
        e._update_master(lambda r: True, ghl_contact_id="c1")
        self.assertEqual(e.handle_inbound("c1"), "stopped")
        self.assertEqual(store.load(self.master)["p1"]["status"], "do_not_contact")
        self.assertEqual(ghl.tagged, ["stop"])
        self.assertEqual(claude.calls, [])
        self.assertIn("nous ne vous écrirons plus", ghl.sent[0][2])

    def test_duplicate_webhook_is_ignored(self):
        ghl = FakeGHL(msgs(("outbound", FIRST), ("inbound", "C'est combien ?")))
        claude = FakeClaude(reply("end_turn", text('{"reply": "Ça dépend…", "intent": "question", "send": true}')))
        e = self.emp(ghl, claude)
        e.handle_inbound("c1")
        self.assertEqual(e.handle_inbound("c1"), "already_answered")
        self.assertEqual(len(ghl.sent), 1)

    def test_slots_are_office_hours_and_booking_needs_an_offered_slot(self):
        e = self.emp(FakeGHL([]))
        t = employee.SetterTools(e, "c1", "Clinique Exemple")
        slots = t.get_free_slots(3)
        labels = [s["label"] for s in slots]
        self.assertIn("lundi 12 octobre à 11h", labels)
        self.assertIn("mardi 13 octobre à 10h30", labels)
        self.assertNotIn(SLOT(13, 20), [s["start_time"] for s in slots])    # 20h: outside office hours
        self.assertNotIn(SLOT(12, 8), [s["start_time"] for s in slots])     # 8h too
        with self.assertRaises(ValueError):
            t.book_call(SLOT(14, 10))

    def test_stop_words(self):
        for t in ("Stop", "merci de ne plus me contacter", "Désinscrivez-moi", "baraka"):
            self.assertTrue(employee.is_stop(t), t)
        self.assertFalse(employee.is_stop("On travaille non-stopper ? ok intéressé"))


class JobsTest(Base):
    def test_due_jobs(self):
        e = self.emp(FakeGHL([]))
        at = lambda h, m, day=9: dt.datetime(2026, 10, day, h, m, tzinfo=TZ)
        self.assertEqual([j for j, _ in e.due_jobs(at(7, 0))], ["followups"])
        self.assertEqual([j for j, _ in e.due_jobs(at(7, 31))], ["daily", "followups"])
        e.state["jobs"].update(daily="2026-10-09", followups="2026-10-09T18")
        self.assertEqual([j for j, _ in e.due_jobs(at(18, 5))], ["report"])
        self.assertIn("pull", [j for j, _ in e.due_jobs(at(4, 0, day=1))])

    def test_email_followups(self):
        store.save(self.master, [{"place_id": "e1", "status": "sent", "sent_channel": "email", "sent_at": "2026-10-06T09:00",
                                  "ghl_contact_id": "c-e1", "followups": "0", "score": "60"}])
        ghl = FakeGHL([])
        e = self.emp(ghl)
        e.job_followups()
        self.assertEqual(len(ghl.sent), 1)
        self.assertIn("Clinique Exemple", ghl.sent[0][2])
        self.assertIn("stop", ghl.sent[0][2])
        e.job_followups()                                   # J+7 not reached yet: nothing more
        self.assertEqual(len(ghl.sent), 1)

    def test_cockpit_lists_dm_followups_and_marks(self):
        e = self.emp(FakeGHL([]))
        self.assertEqual([r["place_id"] for r in e.today_queue()["dm_followups"]], ["p1"])
        self.assertFalse(e.mark("p1", "anything"))
        self.assertTrue(e.mark("p1", "dm_followed_up"))
        self.assertEqual(e.today_queue()["dm_followups"], [])


class HttpTest(Base):
    def test_webhook_auth_and_queue(self):
        inbox = queue.Queue()
        with mock.patch.dict(os.environ, {"EMPLOYEE_KEY": "s3cret"}):
            srv = ThreadingHTTPServer(("127.0.0.1", 0), employee.make_handler(self.emp(FakeGHL([])), inbox))
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{srv.server_address[1]}"
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

        def post(path, body):
            req = urllib.request.Request(base + path, data=json.dumps(body).encode(), method="POST",
                                         headers={"Content-Type": "application/json"})
            try:
                with opener.open(req, timeout=5) as r:
                    return r.status
            except urllib.error.HTTPError as e:
                return e.code
        try:
            self.assertEqual(post("/webhooks/ghl?key=wrong", {"contact_id": "c1"}), 403)
            self.assertEqual(post("/webhooks/ghl?key=s3cret", {"contact": {"id": "c1"}}), 200)
            self.assertEqual(inbox.get_nowait(), "c1")
            with opener.open(base + "/health", timeout=5) as r:
                self.assertEqual(r.status, 200)
        finally:
            srv.shutdown()
            srv.server_close()


if __name__ == "__main__":
    unittest.main()
