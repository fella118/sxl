# Deploying the SOGIXEL AI employee

One always-on service. It answers prospects within seconds, day and night, prepares the morning list, sends email
follow-ups, backs itself up and reports to Saad.

| Role | When | What it does |
|---|---|---|
| Setter | 24/7, seconds after a reply | Claude reads the conversation, answers, offers 2–3 slots, books the call in GHL, or hands over to Saad. Says it is Saad's AI assistant. |
| Hunter | 07:30 | Refreshes the best prospects, builds the queue, Claude polishes each message from verified facts only, sends Saad the cockpit link. |
| Pull | 1st of the month, 03:00 | Finds new clinics (Google Places). |
| Follow-ups | hourly | Email relances at J+3 and J+7 (approved emails only). DM relances are listed in the cockpit. |
| Reporter | 18:00 | Contacted, replies, calls booked, pipeline. |
| Backup | 02:30 | Master list + runtime database, 14 days kept. |

## How it stays safe

- **Shadow mode first.** With `SETTER_MODE=shadow` (the default) every reply is sent to Saad as a draft and nothing
  is booked. Run it like this for a week, read the drafts, then switch to `live`.
- **It never starts a conversation** and only answers conversations that contain Saad's first message
  ("Bonjour, je suis Saad, fondateur de SOGIXEL…") or carry the tag `prospect-sogixel`.
- **It steps back when you step in.** If Saad writes in a conversation himself, the bot stops answering it. Tag a
  contact `bot-pause` in GHL to pause it by hand; `python -m sogixel unpause <contact_id>` hands it back.
- **Limits.** 6 automated replies per conversation per day (then Saad takes over), 150 per day overall (cost guard),
  and no reply to anything that answers in under 15 seconds (a clinic's own auto-responder).
- **"Stop"** is handled instantly without the model, and is permanent.
- **No lost replies.** Every webhook is written to disk before it's processed. After a restart the queue resumes;
  a reply that fails 3 times alerts Saad.
- **Separate keys** for the webhook and the cockpit. The cockpit link puts its key in an HttpOnly cookie on the
  first visit. The webhook payload is never trusted: only the contact ID is used, everything else is re-read from
  GHL.

## 1. Server

1. A small VPS with Docker (1 vCPU / 2 GB is plenty), and a subdomain pointing to it, e.g. `employee.sogixel.ma`.
2. On the server:
   ```bash
   mkdir -p /opt/sogixel/data /opt/sogixel/out && cd /opt/sogixel
   sudo chown -R 1000:1000 data out          # the container runs as a non-root user (uid 1000)
   # copy docker-compose.yml and .env.example from prospector/, then:
   cp .env.example .env && nano .env
   echo <GitHub token with read:packages> | docker login ghcr.io -u fella118 --password-stdin
   docker compose up -d
   docker compose exec employee python -m sogixel check --live
   ```
3. HTTPS is automatic (Caddy). `https://<domain>/health` answers `{"ok": true, ...}`.
4. Free uptime monitoring: point UptimeRobot (or any monitor) at `https://<domain>/health` every 5 minutes.

## 2. GoHighLevel (SOGIXEL sub-account)

1. **Private Integration token** (Settings → Private Integrations). Scopes: contacts (read/write), conversations
   (read/write), conversation messages (write), calendars (read), calendar events (write).
   → `GHL_TOKEN`, sub-account ID → `GHL_LOCATION_ID`.
2. **Connect Instagram @lemrateh_** (and WhatsApp Business if used) in Settings → Integrations.
3. **Calendar** "Appel SOGIXEL", 15 minutes, with your real availability → `GHL_CALENDAR_ID`.
4. **Your own contact** with your WhatsApp number → `GHL_OWNER_CONTACT_ID` (notifications and drafts go there).
5. **Workflow**: trigger "Customer Replied" (Instagram, WhatsApp, Facebook, Email) → action **Webhook**, POST
   `https://<domain>/webhooks/ghl?key=<WEBHOOK_KEY>`, custom data `contact_id` = `{{contact.id}}`.
6. **Email**: a separate sending domain, warmed up for 2–3 weeks before the first approved emails.

If the DMs you send from the Instagram app don't show up in GHL conversations, add the tag `prospect-sogixel` to the
contact when they reply.

## 3. Keys

`ANTHROPIC_API_KEY` (console.anthropic.com), `GOOGLE_PLACES_API_KEY` (Places API (New), restricted to it; set a
daily quota in Google Cloud so the bill can't run away), `META_ADLIB_TOKEN` (optional), `WEBHOOK_KEY` and
`COCKPIT_KEY` (two different random strings, 24+ characters: `openssl rand -hex 24`).

## 4. Go-live checklist

1. `python -m sogixel check --live` is all ✓.
2. First pull: `docker compose exec employee python -m sogixel pull --cities Casablanca --verticals dental`, review.
3. A week in `shadow`: reply from your own test Instagram to one of your DMs; the draft arrives on your WhatsApp.
4. Switch `SETTER_MODE=live` in `.env`, then `docker compose up -d`.

## Releases

Every push runs the tests in GitHub Actions. A merge to `main` builds the image and publishes it to
`ghcr.io/fella118/sogixel-employee`. Roll it out with `scripts/deploy.sh user@server`, which pulls, restarts and
runs the live check. Operations: [RUNBOOK.md](RUNBOOK.md).

## Costs (orders of magnitude)

- Server: a few euros a month (or a free-tier VM).
- Claude: replies on Sonnet 5.5 and the morning rewrite on Haiku 5.5, roughly $0.15–0.20 a day at 20 DMs a day
  (estimate). Models are set per job in `config.toml`; the daily cap bounds the worst case.
- Google Places: within the free monthly quota if `daily.candidates` stays around 30.
