# Deploying the SOGIXEL AI employee

One small always-on service. It answers prospects 24/7, prepares the morning list, sends email follow-ups and reports
to Saad on WhatsApp.

| Role | When | What it does |
|---|---|---|
| Setter | 24/7, seconds after a reply | Claude reads the conversation, answers, offers 2–3 slots, books the call in GHL, or hands over to Saad. Says it is Saad's AI assistant. |
| Hunter | 07:30 | Refreshes the best prospects, builds the queue, Claude polishes every message from verified facts only, WhatsApp to Saad with the cockpit link. |
| Pull | 1st of the month, 03:00 | Finds new clinics (Google Places). |
| Follow-ups | hourly | Email relances at J+3 and J+7 (approved emails only). DM relances are listed in the cockpit. |
| Reporter | 18:00 | Contacted, replies, calls booked, pipeline. |
| Cockpit | your phone | Today's DMs (open profile, copy, "Envoyé ✓"), emails to approve, calls, DM relances. |

**What it never does:** send a first message to anyone, DM on Instagram/WhatsApp on its own, answer a contact we
didn't prospect (clients, friends, suppliers), invent a price or a result, or contact someone who said stop.

## 1. Server (≈15 minutes)

1. Any small VPS with Docker (1 vCPU / 2 GB is plenty).
2. A subdomain pointing to it, e.g. `employee.sogixel.ma` (DNS A record).
3. Copy the `prospector/` folder, then `cp .env.example .env` and fill it in (step 2 below).
4. `docker compose up -d`, then open `https://<domain>/health`: it should say `{"ok": true}`.

HTTPS is automatic (Caddy).

## 2. GoHighLevel (SOGIXEL sub-account)

1. **Private Integration token** (Settings → Private Integrations). Scopes: contacts (read/write), conversations
   (read/write), conversation messages (write), calendars (read), calendar events (write).
   → `GHL_TOKEN`, and the sub-account ID → `GHL_LOCATION_ID`.
2. **Connect Instagram @lemrateh_** (and WhatsApp Business if used) in Settings → Integrations.
3. **Calendar** "Appel SOGIXEL", 15 minutes, with your real availability → `GHL_CALENDAR_ID`.
4. **Your own contact** with your WhatsApp number → `GHL_OWNER_CONTACT_ID` (notifications go there).
5. **Workflow**, trigger "Customer Replied" (Instagram, WhatsApp, Facebook, Email) → action **Webhook**, POST
   `https://<domain>/webhooks/ghl?key=<EMPLOYEE_KEY>`, custom data `contact_id` = `{{contact.id}}`.
6. **Email**: a separate sending domain, warmed up for 2–3 weeks before the first approved emails.

The setter only answers a conversation if it contains your first message ("Bonjour, je suis Saad, fondateur de
SOGIXEL…") or the contact has the tag `prospect-sogixel`. If the DMs you send from the Instagram app don't show up
in GHL conversations, add that tag to the contact when they reply.

## 3. Keys

`ANTHROPIC_API_KEY` (console.anthropic.com), `GOOGLE_PLACES_API_KEY` (Places API (New), restricted to it),
`META_ADLIB_TOKEN` (optional, see README), `EMPLOYEE_KEY` (any long random string; keep the cockpit link private).

## 4. First run

```bash
docker compose exec employee python -m sogixel pull --cities Casablanca --verticals dental
docker compose exec employee python -m sogixel stats
```

Review those clinics, tune `config.toml` if needed, then let the schedule run. Logs: `docker compose logs -f employee`.

## Costs (orders of magnitude)

- Server: a few euros a month.
- Claude (Opus 5.5): a handled reply is a few thousand tokens, roughly ten cents; the morning polish of ~50
  messages runs at low effort.
- Google Places: one Place Details call per candidate each morning (`daily.candidates` in `config.toml`); lower it
  to cut the bill.
