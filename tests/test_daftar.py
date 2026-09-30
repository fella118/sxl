import base64
import json
import threading
import urllib.request
from datetime import date, timedelta
from http.server import ThreadingHTTPServer
from types import SimpleNamespace as NS

import pytest

from daftar import seed, templates
from daftar.agent import Assistant
from daftar.server import App, make_handler
from daftar.service import Service
from daftar.store import Store

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
)


def text(t):
    return NS(type="text", text=t)


def tool(id_, name, **input_):
    return NS(type="tool_use", id=id_, name=name, input=input_)


def resp(*content, stop="end_turn"):
    usage = NS(input_tokens=1000, output_tokens=200, cache_read_input_tokens=500, cache_creation_input_tokens=0)
    return NS(content=list(content), stop_reason=stop, usage=usage)


class FakeLLM:
    """Replays scripted responses and records every request."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.requests = []
        self.beta = NS(messages=NS(create=self._create))

    def _create(self, **kwargs):
        self.requests.append(kwargs)
        return self.responses.pop(0)


@pytest.fixture
def make(tmp_path):
    def _make(*responses):
        store = Store()
        seed.seed(store)
        llm = FakeLLM(*responses)
        assistant = Assistant(store, llm, seed.FIRM, seed.DEADLINE_DAY)
        service = Service(store, assistant, firm=seed.FIRM, deadline_day=seed.DEADLINE_DAY, files_dir=tmp_path)
        return store, service, llm
    return _make


def test_kickoff_sends_one_template_per_client_in_their_language(make):
    store, service, _ = make()
    assert service.period() == "2026-09"
    assert service.kickoff() == len(seed.CLIENTS)
    assert service.kickoff() == 0  # idempotent

    boul = store.messages("BOUL01")
    assert len(boul) == 1 and boul[0]["kind"] == "template"
    assert boul[0]["body"].startswith("Salam Si Ahmed")
    assert "l'état dyal l'khlass" in boul[0]["body"]
    assert store.messages("TRANS02")[0]["body"].startswith("Bonjour Mme Fatima Zahra")
    assert "Paie" not in store.messages("CAFE03")[0]["body"]  # café has no payroll
    assert store.pending_followup("BOUL01")["due"] == "2026-10-04"


def test_reply_with_photo_ticks_checklist_and_schedules_promise(make):
    store, service, llm = make(
        resp(
            tool("t1", "update_checklist", doc_type="releve_bancaire", status="received", file_ids=[1], note="relevé complet"),
            tool("t2", "schedule_followup", date="2026-10-03", reason="a promis la paie pour demain"),
            stop="tool_use",
        ),
        resp(text("Choukran Si Ahmed, wsel relevé. Mazal khassna les factures w l paie.")),
    )
    service.kickoff()
    reply = service.receive("BOUL01", "ha relevé, l paie ghda inchallah", [("releve.png", "image/png", PNG)])

    assert reply.startswith("Choukran Si Ahmed")
    status = {r["doc_type"]: r["status"] for r in store.checklist("BOUL01", "2026-09")}
    assert status["releve_bancaire"] == "received"
    assert status["etat_paie"] == "missing"
    assert store.file(1)["doc_type"] == "releve_bancaire"
    assert store.pending_followup("BOUL01")["due"] == "2026-10-03"
    assert store.messages("BOUL01")[-1]["body"] == reply

    first = llm.requests[0]
    assert first["model"] == "claude-opus-5-5"
    assert first["fallbacks"] == "default" and "tool_choice" not in first
    kinds = [b["type"] for b in first["messages"][0]["content"]]
    assert "image" in kinds
    # tool results go back in one user message
    results = llm.requests[1]["messages"][-1]["content"]
    assert [r["tool_use_id"] for r in results] == ["t1", "t2"]
    assert not any(r["is_error"] for r in results)
    assert store.total_cost_usd() == pytest.approx(2 * (1000 * 4 + 200 * 20 + 500 * 0.2) / 1e6)


def test_invalid_tool_input_is_returned_as_error(make):
    store, service, llm = make(
        resp(tool("t1", "schedule_followup", date="2026-09-01", reason="passé"), stop="tool_use"),
        resp(text("D'accord.")),
    )
    service.receive("TRANS02", "je vous envoie ça bientôt")
    result = llm.requests[1]["messages"][-1]["content"][0]
    assert result["is_error"] and "between" in result["content"]
    # the safety net still schedules a reminder
    assert store.pending_followup("TRANS02")["due"] == "2026-10-03"


def test_questions_are_flagged_not_answered(make):
    store, service, _ = make(
        resp(tool("t1", "flag_for_accountant", reason="Question sur le montant de TVA"), stop="tool_use"),
        resp(text("Si Mustapha, l'comptable ghadi yjawbek 3la had so2al.")),
    )
    service.receive("CAFE03", "ch7al khassni nkhelles TVA?")
    assert [f["reason"] for f in store.flags("CAFE03")] == ["Question sur le montant de TVA"]


def test_refusal_goes_to_a_human(make):
    store, service, _ = make(resp(stop="refusal"))
    assert service.receive("GARG06", "...") == ""
    assert store.flags("GARG06")


def test_reminders_escalate_then_flag_when_late(make):
    store, service, _ = make()
    service.kickoff()
    sent_days = []
    for _ in range(12):  # 1 Oct -> 13 Oct
        if service.advance_day() and store.messages("PHAR04")[-1]["kind"] == "template":
            sent_days.append(store.today.isoformat())
    bodies = [m["body"] for m in store.messages("PHAR04")]
    assert sent_days == ["2026-10-04", "2026-10-07", "2026-10-09", "2026-10-11", "2026-10-13"]
    assert bodies[1].startswith("Bonjour Dr Bennani, petit rappel")
    assert bodies[3].startswith("Dr Bennani, dernier rappel")  # 9 Oct: within 2 days of the 10 Oct deadline
    late = [f for f in store.flags("PHAR04") if "en retard" in f["reason"]]
    assert len(late) == 1


def test_complete_file_stops_reminders(make):
    store, service, _ = make(
        *[resp(tool(f"t{i}", "update_checklist", doc_type=d, status="received", file_ids=[], note=""), stop="tool_use")
          for i, d in enumerate(["releve_bancaire", "factures_achats"])],
        resp(tool("t9", "update_checklist", doc_type="factures_ventes", status="not_applicable", file_ids=[], note="pas de ventes"),
             stop="tool_use"),
        resp(text("Choukran, kolchi wsel.")),
    )
    service.kickoff()
    service.receive("GARG06", "hahoma kamlin, w ma bi3t walou had chhar")
    assert service.report()["clients"][3]["complete"] is True  # alphabetical: Garage Nour is 4th
    assert store.pending_followup("GARG06") is None
    for _ in range(10):
        service.advance_day()
    assert [m["kind"] for m in store.messages("GARG06")].count("template") == 1


def test_rejects_unsupported_files(make):
    _, service, _ = make()
    with pytest.raises(ValueError):
        service.receive("BOUL01", "", [("virus.exe", "application/x-msdownload", b"MZ")])


def test_templates_cover_every_level_and_language():
    for language in templates.TEMPLATES:
        for level in range(templates.MAX_LEVEL + 1):
            out = templates.render(level, language, contact="Si X", firm="F", period="2026-09",
                                   docs=["releve_bancaire"], deadline="10/10")
            assert "Si X" in out and "{" not in out


def test_http_api_end_to_end(tmp_path):
    llm = FakeLLM(resp(text("Merci, bien reçu.")))
    app = App(tmp_path / "d.db", tmp_path / "files", llm=llm)
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(app))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}"

    def post(path, body):
        req = urllib.request.Request(base + path, json.dumps(body).encode(), {"Content-Type": "application/json"})
        return json.load(urllib.request.urlopen(req))

    try:
        assert json.load(urllib.request.urlopen(base + "/api/state"))["totals"]["clients"] == 6
        assert post("/api/kickoff", {})["sent"] == 6
        out = post("/api/message", {"client": "TRANS02", "text": "voici",
                                    "files": [{"name": "../../r.png", "mime": "image/png",
                                               "data": base64.b64encode(PNG).decode()}]})
        assert out["reply"] == "Merci, bien reçu."
        f = app.store.file(1)
        assert (tmp_path / "files") in __import__("pathlib").Path(f["path"]).resolve().parents
        assert urllib.request.urlopen(base + "/api/file/1").read() == PNG
        with pytest.raises(urllib.error.HTTPError):
            urllib.request.urlopen(base + "/api/file/99")
        assert "Daftar" in urllib.request.urlopen(base + "/").read().decode()
    finally:
        server.shutdown()
