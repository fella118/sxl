# Daftar

**Your clients send their papers on time, and you stop chasing them.**

Daftar is a WhatsApp assistant for Moroccan fiduciaires (cabinets comptables). Every month it asks each client for their documents, understands their replies in Darija, French or Arabic, sorts the photos and PDFs they send, keeps following up until the file is complete, and gives the owner one checklist of what is still missing.

It never reads amounts and never does accounting. The worst it can do is send a reminder, so it's easy to trust.

## Try the demo

```bash
pip install -e .
export ANTHROPIC_API_KEY=sk-ant-...
daftar demo            # then open http://127.0.0.1:8000
```

The demo runs a fictional firm, *Atlas Conseil*, with 6 clients, collecting their September 2026 documents during October. The deadline is the 10th.

1. **Lancer la relance du mois** sends the monthly reminder to every client. This is a WhatsApp-approved template in the client's language.
2. Click a client and **write as the client** in the phone on the right. You can type Darija ("ghda nsiftlik relevé"), attach a photo or PDF of a document, ask a tax question, or say there were no sales this month. The assistant (Claude Opus 5.5) updates the checklist, schedules the next reminder based on what the client promised, and replies the way the client writes.
3. **Jour suivant ▶** moves the clock forward one day. Reminders go out when they're due and get firmer as the deadline approaches. Files still incomplete after the deadline appear under *À traiter par un humain*.
4. **Réinitialiser** starts the demo over.

Demo data (database and received files) lives in `./demo-data/`.

## How it works

| Piece | Role |
|---|---|
| `daftar/templates.py` | The reminders the firm sends first. WhatsApp only allows pre-approved templates to open a conversation, so these are fixed texts (4 levels × Darija/French). |
| `daftar/agent.py` | Claude Opus 5.5 reads the client's reply and files, then uses three tools: `update_checklist`, `schedule_followup`, `flag_for_accountant`. Anything that isn't document collection (tax questions, fees, complaints) goes to a human. |
| `daftar/service.py` | The monthly cycle: kickoff, inbound messages, due follow-ups, escalation, late-file flags, and the owner report. Plain code with no AI. |
| `daftar/store.py` | SQLite: clients, checklist, messages, files, follow-ups, flags, AI cost per client. |
| `daftar/server.py` + `static/index.html` | The demo web app (standard library only). |

Every Claude call is logged with its cost, so the dashboard shows what a month of collection really costs per firm.

## Not built yet (for a real pilot)

- **WhatsApp Cloud API connection:** a webhook that calls `Service.receive()`, and a `send` hook that sends messages through the API. The four reminder templates also need Meta's approval.
- **Syncing received files** to the firm's Google Drive or shared folder.
- A daily job (cron) that runs `Service.run_followups()`, plus the monthly kickoff.
- Multiple firms (multi-tenant) and a login.

## Tests

```bash
pip install -e '.[dev]'
pytest
```

The tests use a scripted stand-in for Claude, so they need no API key.
