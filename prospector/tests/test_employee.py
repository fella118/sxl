"""AI employee tests: Claude and GoHighLevel are faked, nothing leaves the machine."""
import datetime as dt
import json
import os
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from types import SimpleNamespace as NS
from unittest import mock
from zoneinfo import ZoneInfo

from sogixel import __main__ as cli, brain, doctor, employee, store
from sogixel.ops import Ops

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
        self.messages = NS(create=self._create)

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
        mid = f"out{len(self.sent)}"
        if cid != "owner":
            self._history.append({"id": mid, "direction": "outbound", "body": text, "type": "", "date": ""})
        return {"messageId": mid}

    def free_slots(self, cal, start, end, tz):
        return [SLOT(12, 8), SLOT(12, 11), SLOT(12, 15), SLOT(13, 10, 30), SLOT(13, 20)]

    def book(self, cal, cid, start, title):
        self.booked.append(start)

    def add_tags(self, cid, tags):
        self.tagged += tags

    def upsert_contact(self, **f):
        return {"id": "c-email"}


def msgs(*pairs):
    return [{"id": f"m{i}", "direction": d, "body": b, "type": "TYPE_INSTAGRAM", "date": f"2026-10-0{i + 1}T10:00:00Z"}
            for i, (d, b) in enumerate(pairs)]


def answer(text_, intent="question"):
    return reply("end_turn", text(json.dumps({"reply": text_, "intent": intent, "send": True})))


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.master = os.path.join(self.tmp.name, "data", "prospects.csv")
        self.out = os.path.join(self.tmp.name, "out")
        store.save(self.master, [{"place_id": "p1", "vertical": "dental", "city": "Casablanca", "score": "75",
                                  "tier": "Hot", "flags": "no_tracking", "ig_handle": "clinique.exemple",
                                  "status": "sent", "sent_channel": "dm", "sent_at": "2026-10-05T10:00",
                                  "ghl_contact_id": "c1"}])

        self.dbs = []

    def tearDown(self):
        for db in self.dbs:
            db.close()
        self.tmp.cleanup()

    def emp(self, ghl, claude=None, mode="live"):
        b = brain.Brain(client=claude) if claude else None
        e = employee.Employee(CFG, self.master, self.out, ghl=ghl, brain=b, now=lambda: NOW, mode=mode)
        e.owner_id = "owner"
        self.dbs.append(e.ops)
        return e


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

    def test_haiku_is_called_without_the_fallback_parameter(self):
        claude = FakeClaude(reply("end_turn", text('{"dm": "Bonjour", "email_body": "Bonjour"}')))
        b = brain.Brain(client=claude, polish_model="claude-haiku-5-5")
        self.assertEqual(b.polish("facts", "dm", "body"), ("Bonjour", "Bonjour"))
        self.assertEqual(claude.calls[0]["model"], "claude-haiku-5-5")
        self.assertNotIn("fallbacks", claude.calls[0])

    def test_polish_keeps_drafts_on_bad_output(self):
        b = brain.Brain(client=FakeClaude(reply("end_turn", text("not json"))))
        self.assertEqual(b.polish("facts", "dm", "body"), ("dm", "body"))


class SetterTest(Base):
    def test_answers_our_conversation_and_books(self):
        ghl = FakeGHL(msgs(("outbound", FIRST), ("inbound", "Intéressant. On peut en parler quand ?")))
        claude = FakeClaude(
            reply("tool_use", tool("t1", "get_free_slots", {"days_ahead": 3})),
            reply("tool_use", tool("t2", "book_call", {"start_time": SLOT(12, 11)})),
            answer("Parfait, lundi 12 octobre à 11h.", "booked"))
        e = self.emp(ghl, claude)
        self.assertEqual(e.handle_inbound("c1"), "booked")
        self.assertEqual(ghl.sent[0], ("c1", "instagram", "Parfait, lundi 12 octobre à 11h."))
        self.assertEqual(ghl.booked, [SLOT(12, 11)])
        self.assertEqual(store.load(self.master)["p1"]["status"], "call_booked")
        self.assertIn("PROSPECT] Intéressant", claude.calls[0]["messages"][0]["content"])
        self.assertIn("Appel réservé", ghl.sent[-1][2])                     # Saad is told

    def test_shadow_mode_drafts_to_saad_and_books_nothing(self):
        ghl = FakeGHL(msgs(("outbound", FIRST), ("inbound", "Ok, lundi 11h ?")))
        claude = FakeClaude(reply("tool_use", tool("t1", "get_free_slots", {"days_ahead": 3})),
                            reply("tool_use", tool("t2", "book_call", {"start_time": SLOT(12, 11)})),
                            answer("C'est noté pour lundi à 11h.", "booked"))
        e = self.emp(ghl, claude, mode="shadow")
        e.handle_inbound("c1")
        self.assertEqual([c for c, _, _ in ghl.sent], ["owner"])            # nothing reached the prospect
        self.assertIn("Brouillon pour Clinique Exemple", ghl.sent[0][2])
        self.assertIn("réservation simulée", ghl.sent[0][2])
        self.assertEqual(ghl.booked, [])
        self.assertEqual(store.load(self.master)["p1"]["status"], "replied")

    def test_never_answers_someone_we_did_not_prospect(self):
        claude = FakeClaude()
        ghl = FakeGHL(msgs(("inbound", "Salam, c'est pour mon rendez-vous de demain")))
        self.assertEqual(self.emp(ghl, claude).handle_inbound("c9"), "not_a_prospect")
        self.assertEqual((ghl.sent, claude.calls), ([], []))

    def test_stop_is_handled_without_the_model(self):
        claude = FakeClaude()
        ghl = FakeGHL(msgs(("outbound", FIRST), ("inbound", "STOP merci")))
        self.assertEqual(self.emp(ghl, claude).handle_inbound("c1"), "stopped")
        self.assertEqual(store.load(self.master)["p1"]["status"], "do_not_contact")
        self.assertEqual(ghl.tagged, ["stop"])
        self.assertEqual(claude.calls, [])
        self.assertEqual(ghl.sent[0][2], employee.STOP_REPLY)

    def test_duplicate_webhook_is_ignored(self):
        ghl = FakeGHL(msgs(("outbound", FIRST), ("inbound", "C'est combien ?")))
        e = self.emp(ghl, FakeClaude(answer("Ça dépend de la clinique…")))
        e.handle_inbound("c1")
        self.assertEqual(e.handle_inbound("c1"), "already_answered")
        self.assertEqual(len(ghl.sent), 1)

    def test_saad_jumping_in_pauses_the_bot(self):
        ghl = FakeGHL(msgs(("outbound", FIRST), ("inbound", "Intéressé"), ("outbound", "Je vous appelle demain, Saad"),
                           ("inbound", "Parfait")))
        claude = FakeClaude()
        e = self.emp(ghl, claude)
        self.assertEqual(e.handle_inbound("c1"), "human_takeover")
        ghl._history.append({"id": "m9", "direction": "inbound", "body": "À demain", "type": "", "date": ""})
        self.assertEqual(e.handle_inbound("c1"), "paused")
        self.assertEqual((ghl.sent, claude.calls), ([], []))

    def test_the_bots_own_replies_are_not_a_takeover(self):
        ghl = FakeGHL(msgs(("outbound", FIRST), ("inbound", "C'est combien ?")))
        e = self.emp(ghl, FakeClaude(answer("Ça dépend de la clinique, on en parle 10 min ?"), answer("Super.")))
        e.handle_inbound("c1")
        ghl._history.append({"id": "m9", "direction": "inbound", "body": "Ok pourquoi pas", "type": "", "date": ""})
        self.assertEqual(e.handle_inbound("c1"), "question")

    def test_pause_tag(self):
        ghl = FakeGHL(msgs(("outbound", FIRST), ("inbound", "Salut")), tags=["bot-pause"])
        self.assertEqual(self.emp(ghl, FakeClaude()).handle_inbound("c1"), "paused")

    def test_per_contact_cap_hands_over(self):
        ghl = FakeGHL(msgs(("outbound", FIRST), ("inbound", "Encore une question")))
        e = self.emp(ghl, FakeClaude())
        e.ops.bump(NOW.date().isoformat(), "ai:c1", CFG["employee"]["max_replies_per_contact_day"])
        self.assertEqual(e.handle_inbound("c1"), "capped")
        self.assertTrue(e.ops.paused("c1"))
        self.assertIn("je te laisse la main", ghl.sent[0][2])

    def test_auto_responder_does_not_start_a_loop(self):
        history = msgs(("outbound", FIRST), ("inbound", "Bonjour"))
        history += [{"id": "b1", "direction": "outbound", "body": "Merci ! Une question ?", "type": "", "date": "2026-10-09T20:00:00Z"},
                    {"id": "m8", "direction": "inbound", "body": "Merci pour votre message, nous revenons vers vous.",
                     "type": "", "date": "2026-10-09T20:00:04Z"}]
        claude = FakeClaude()
        e = self.emp(FakeGHL(history), claude)
        e.ops.record_sent("c1", "b1", "Merci ! Une question ?")
        self.assertEqual(e.handle_inbound("c1"), "auto_reply_suspected")
        self.assertEqual(claude.calls, [])

    def test_slots_are_office_hours_and_booking_needs_an_offered_slot(self):
        t = employee.SetterTools(self.emp(FakeGHL([])), "c1", "Clinique Exemple")
        labels = [s["label"] for s in t.get_free_slots(3)]
        self.assertEqual(labels, ["lundi 12 octobre à 11h", "lundi 12 octobre à 15h", "mardi 13 octobre à 10h30"])
        with self.assertRaises(ValueError):
            t.book_call(SLOT(14, 10))

    def test_stop_words(self):
        for t in ("Stop", "merci de ne plus me contacter", "Désinscrivez-moi", "baraka"):
            self.assertTrue(employee.is_stop(t), t)
        self.assertFalse(employee.is_stop("On travaille non-stopper ? ok intéressé"))


class InboxTest(Base):
    def test_events_survive_a_crash_and_failures_retry_then_alert(self):
        e = self.emp(FakeGHL([]))
        e.ops.enqueue("c1")
        e.ops.claim()                                     # crash while processing...
        again = Ops(e.ops.path)                           # ...restart: the event is pending again
        self.dbs.append(again)
        self.assertEqual(again.pending(), 1)
        e.ops = again
        with mock.patch.object(e, "handle_inbound", side_effect=RuntimeError("GHL down")), \
             mock.patch.object(employee.time, "sleep"):
            employee.process_inbox(e)
        self.assertEqual(e.ops.pending(), 0)
        self.assertIn("pas pu répondre", e.ghl.sent[-1][2])
        self.assertEqual(len(e.ghl.sent), 1)              # one alert after the last attempt, not three


class JobsTest(Base):
    def test_due_jobs(self):
        e = self.emp(FakeGHL([]))
        at = lambda h, m, day=9: dt.datetime(2026, 10, day, h, m, tzinfo=TZ)
        self.assertEqual([j for j, _ in e.due_jobs(at(2, 0))], ["followups"])
        self.assertEqual([j for j, _ in e.due_jobs(at(7, 31))], ["backup", "daily", "followups"])
        for name, key in (("backup", "2026-10-09"), ("daily", "2026-10-09"), ("followups", "2026-10-09T18")):
            e.ops.record_job(name, key, True)
        self.assertEqual([j for j, _ in e.due_jobs(at(18, 5))], ["report"])
        self.assertIn("pull", [j for j, _ in e.due_jobs(at(4, 0, day=1))])

    def test_failed_job_is_recorded_and_reported(self):
        e = self.emp(FakeGHL([]))
        with mock.patch.object(e, "_cli", side_effect=SystemExit("Places API 403")):
            e.run_job("daily", "2026-10-09")
        self.assertFalse(e.ops.jobs()["daily"]["ok"])
        self.assertIn("a échoué", e.ghl.sent[-1][2])

    def test_fresh_install_asks_for_the_first_pull_once(self):
        store.save(self.master, [])
        e = self.emp(FakeGHL([]))
        e.run_job("daily", "2026-10-09")
        e.run_job("daily", "2026-10-09")
        self.assertTrue(e.ops.jobs()["daily"]["ok"])
        self.assertEqual([t for _, _, t in e.ghl.sent], ["La liste de cliniques est vide : lance le premier pull (voir DEPLOY.md)."])

    def test_email_followups_live_only(self):
        store.save(self.master, [{"place_id": "e1", "status": "sent", "sent_channel": "email", "sent_at": "2026-10-06T09:00",
                                  "ghl_contact_id": "c-e1", "followups": "0", "score": "60"}])
        ghl = FakeGHL([])
        self.emp(ghl, mode="shadow").job_followups()
        self.assertEqual(ghl.sent, [])
        e = self.emp(ghl)
        e.job_followups()
        self.assertEqual(len(ghl.sent), 1)
        self.assertIn("Clinique Exemple", ghl.sent[0][2])
        self.assertIn("stop", ghl.sent[0][2])
        e.job_followups()                                   # J+7 not reached yet
        self.assertEqual(len(ghl.sent), 1)

    def test_backup_keeps_n_days(self):
        e = self.emp(FakeGHL([]))
        root = os.path.join(os.path.dirname(self.master), "backups")
        for d in range(1, 20):
            os.makedirs(os.path.join(root, f"2026-09-{d:02d}"))
        e.job_backup()
        kept = sorted(os.listdir(root))
        self.assertEqual(len(kept), CFG["employee"]["backup_keep_days"])
        self.assertEqual(kept[-1], "2026-10-09")
        self.assertTrue(os.path.exists(os.path.join(root, "2026-10-09", "employee.db")))
        self.assertTrue(os.path.exists(os.path.join(root, "2026-10-09", "prospects.csv")))

    def test_cockpit_lists_dm_followups_and_marks(self):
        e = self.emp(FakeGHL([]))
        self.assertEqual([r["place_id"] for r in e.today_queue()["dm_followups"]], ["p1"])
        self.assertFalse(e.mark("p1", "anything"))
        self.assertTrue(e.mark("p1", "dm_followed_up"))
        self.assertEqual(e.today_queue()["dm_followups"], [])


class HttpTest(Base):
    def setUp(self):
        super().setUp()
        env = {"WEBHOOK_KEY": "w" * 24, "COCKPIT_KEY": "c" * 24}
        self.env = mock.patch.dict(os.environ, env)
        self.env.start()
        self.emp_ = self.emp(FakeGHL([]))
        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), employee.make_handler(self.emp_))
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.base = f"http://127.0.0.1:{self.srv.server_address[1]}"

        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *a, **k):
                return None
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect)

    def tearDown(self):
        self.srv.shutdown()
        self.srv.server_close()
        self.env.stop()
        super().tearDown()

    def call(self, path, body=None, headers=None):
        req = urllib.request.Request(self.base + path, data=None if body is None else json.dumps(body).encode(),
                                     method="GET" if body is None else "POST", headers=headers or {})
        try:
            with self.opener.open(req, timeout=5) as r:
                return r.status, dict(r.headers), r.read()
        except urllib.error.HTTPError as e:
            return e.code, dict(e.headers), e.read()

    def test_webhook_needs_the_webhook_key_and_stores_the_event(self):
        self.assertEqual(self.call("/webhooks/ghl?key=" + "c" * 24, {"contact_id": "c1"})[0], 403)   # cockpit key ≠ webhook key
        self.assertEqual(self.call("/webhooks/ghl?key=" + "w" * 24, {"contact": {"id": "c1"}})[0], 200)
        self.assertEqual(self.emp_.ops.claim()["contact_id"], "c1")
        self.assertEqual(self.call("/webhooks/ghl?key=" + "w" * 24, {"x": "y" * 70000})[0], 413)

    def test_cockpit_login_moves_the_key_into_a_cookie(self):
        code, headers, _ = self.call("/cockpit?key=" + "c" * 24)
        self.assertEqual((code, headers["Location"]), (302, "/cockpit"))
        self.assertIn("HttpOnly", headers["Set-Cookie"])
        self.assertEqual(self.call("/cockpit")[0], 403)
        self.assertEqual(self.call("/api/today", headers={"Cookie": "sx=" + "c" * 24})[0], 200)
        self.assertEqual(self.call("/status", headers={"Cookie": "sx=" + "w" * 24})[0], 403)

    def test_health_is_public_and_minimal(self):
        code, _, body = self.call("/health")
        self.assertEqual((code, json.loads(body)), (200, {"ok": True, "mode": "live", "pending": 0}))


class DoctorTest(unittest.TestCase):
    def test_missing_configuration_fails_and_full_configuration_passes(self):
        with tempfile.TemporaryDirectory() as d, mock.patch("builtins.print"):
            with mock.patch.dict(os.environ, {}, clear=True):
                self.assertEqual(doctor.run(CFG, d), 1)
            env = {k: "x" for k, _ in doctor.REQUIRED} | {"EMPLOYEE_KEY": "k" * 32}
            with mock.patch.dict(os.environ, env, clear=True):
                self.assertEqual(doctor.run(CFG, d), 0)


if __name__ == "__main__":
    unittest.main()
