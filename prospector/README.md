# SOGIXEL prospector

Finds high-ticket clinics in Morocco (aesthetic medicine, hair transplant, implant/aesthetic dentistry), checks what
they're missing, scores them, and builds each morning's outreach list with ready-to-send first messages.

**The AI prepares; a human sends the first message.** The AI employee (`python -m sogixel serve`, see
[DEPLOY.md](DEPLOY.md)) then answers replies 24/7, books calls and sends email follow-ups. It never starts a
conversation and never answers anyone we didn't prospect.

## Daily flow

1. **Find**: Google Places API, all target clinics per city (`pull`, run once, then monthly).
2. **Audit**: one polite request to each clinic's own homepage (robots.txt respected). Checks for a Meta pixel, Tag
   Manager, booking tool, WhatsApp button, an agency CRM, plus the Instagram handle and generic email they publish.
   If the site uses Tag Manager, its public container is read too: that's where most Meta pixels and Google Ads tags
   are hidden.
3. **Ad history**: see below.
4. **Score**: fit (established / new opening / city) + pain (reviews saying nobody answers, no tracking, no
   booking, no WhatsApp). Each point has a reason in French. Hot ≥ 60, Warm ≥ 40.
5. **Queue** (`daily`): best open prospects get a fresh check, then up to 20 DMs, 20 emails and 10 calls are queued
   with a first message built on one true finding.
6. **Saad sends** the DMs by hand from the queue sheet (profile link + message ready, ~10 min for 20) and marks
   `status`: `envoyé`, `répondu`, `appel pris`, `client`, `pas intéressé`, `stop`.
7. **Sync** (`sync`) brings those statuses back into the master list. `stop` is permanent.

## Ad history (past and current advertisers)

| Source | What it shows | How |
|---|---|---|
| Pixels and ad tags on the site, incl. inside Tag Manager | Has paid for Meta / Google ads at some point (budget proven) | Automatic |
| Meta Ad Library API | Every Meta ad that reached the EU in the last 12 months, active or stopped, with dates: the clinics chasing MRE and medical tourists | Automatic (`META_ADLIB_TOKEN`) |
| Meta Ad Library, Morocco | Ads shown only in Morocco aren't in the API | One-click link per clinic (`ad_library_url`) |
| Google Ads Transparency Center | Google / YouTube ads with first and last shown dates | One-click link per clinic by domain (`google_ads_url`); Google has no API for Morocco |

Scoring: ad tags = +12 (they have budget). Meta ads to Europe = +10, and +10 more if they **stopped**: that becomes
the message angle ("vos pubs vers l'Europe se sont arrêtées le 2 mai : souvent parce qu'on ne voit pas ce qu'elles
rapportent"). Spending on ads with no tag at all = the `no_tracking` angle.

## Setup

- `GOOGLE_PLACES_API_KEY`: environment variable (cloud environment settings → Edit). Enable "Places API (New)" in
  Google Cloud and restrict the key to it.
- `META_ADLIB_TOKEN` (optional, for ad history): confirm identity at facebook.com/ID, create a Meta developer app,
  generate a user access token (long-lived tokens last 60 days). Without it, the links are still in the queue.
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

## The AI employee (24/7)

`python -m sogixel serve` runs everything above on a schedule and adds the setter: when a prospect replies on
Instagram, WhatsApp or email, GoHighLevel calls the webhook and Claude answers within seconds, proposes slots from
the GHL calendar, books the call, or hands over to Saad on WhatsApp. "Stop" is handled instantly without the model.
Saad works from the cockpit page on his phone. Setup: [DEPLOY.md](DEPLOY.md).

## Rules built in

- **Google Maps terms**: the master list stores place IDs and our own findings only. Names, phones and reviews are
  fetched fresh for the day's queue.
- **Loi 09-08 (Morocco)**: only role addresses (`contact@`, `info@`, `rdv@`...) are kept for email. Named personal
  addresses are counted, never stored. Every email carries an opt-out, and `stop` closes the prospect forever.
  Declare the prospect file to the CNDP.
- **Instagram / WhatsApp**: no automated sending. The first message is sent by a person. Automation only starts
  after the clinic replies (GHL workflows).
- **Messages**: one verifiable fact, one question, no link. The daily Claude rewrite may only use the `facts` column.
