# SOGIXEL prospector

Finds high-ticket clinics in Morocco (aesthetic medicine, hair transplant, implant/aesthetic dentistry), checks what
they're missing, scores them, and builds each morning's outreach list with ready-to-send first messages.

**The AI prepares; a human sends.** Nothing in this repo sends a DM, an email or a WhatsApp to a prospect.

## Daily flow

1. **Find**: Google Places API, all target clinics per city (`pull`, run once, then monthly).
2. **Audit**: one polite request to each clinic's own homepage (robots.txt respected). Checks for a Meta pixel, Tag
   Manager, booking tool, WhatsApp button, an agency CRM, plus the Instagram handle and generic email they publish.
3. **Score**: fit (established / new opening / city) + pain (reviews saying nobody answers, no tracking, no
   booking, no WhatsApp). Each point has a reason in French. Hot ≥ 60, Warm ≥ 40.
4. **Queue** (`daily`): best open prospects get a fresh check, then up to 20 DMs, 20 emails and 10 calls are queued
   with a first message built on one true finding.
5. **Saad sends** the DMs by hand from the queue sheet (profile link + message ready, ~10 min for 20) and marks
   `status`: `envoyé`, `répondu`, `appel pris`, `client`, `pas intéressé`, `stop`.
6. **Sync** (`sync`) brings those statuses back into the master list. `stop` is permanent.

## Setup

- `GOOGLE_PLACES_API_KEY`: environment variable (cloud environment settings → Edit). Enable "Places API (New)" in
  Google Cloud and restrict the key to it.
- Python 3.11+, standard library only.

```bash
cd prospector
python -m sogixel pull                       # all cities and verticals in config.toml
python -m sogixel pull --cities Casablanca --verticals dental   # smaller first run
python -m sogixel daily                      # -> out/<date>/queue.csv + report.md
python -m sogixel sync out/*/queue.csv
python -m sogixel stats
python -m unittest discover -s tests -t .    # offline tests
```

`data/` and `out/` are git-ignored: prospect data lives in Drive, not in the repo.

## Rules built in

- **Google Maps terms**: the master list stores place IDs and our own findings only. Names, phones and reviews are
  fetched fresh for the day's queue.
- **Loi 09-08 (Morocco)**: only role addresses (`contact@`, `info@`, `rdv@`...) are kept for email. Named personal
  addresses are counted, never stored. Every email carries an opt-out, and `stop` closes the prospect forever.
  Declare the prospect file to the CNDP.
- **Instagram / WhatsApp**: no automated sending. The first message is sent by a person. Automation only starts
  after the clinic replies (GHL workflows).
- **Messages**: one verifiable fact, one question, no link. The daily Claude rewrite may only use the `facts` column.
