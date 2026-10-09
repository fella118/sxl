"""Master list (CSV, synced to Drive by the daily run). Holds place IDs + our own findings only."""
import csv
import os

MASTER_COLS = ["place_id", "vertical", "city", "score", "tier", "angle", "flags", "ig_handle", "email_generic",
               "status", "first_seen", "last_checked", "last_queued", "notes", "maps_link"]
QUEUE_COLS = ["date", "rank", "channel", "tier", "score", "vertical", "city", "name", "instagram_url", "email",
              "phone", "maps_url", "website", "ad_library_url", "reasons", "facts", "dm", "email_subject",
              "email_body", "call_opener", "place_id", "status"]
# Saad edits `status` in the sheet. Rows in CLOSED are never contacted again.
OPEN = {"new", "queued"}
CLOSED = {"sent", "replied", "call_booked", "client", "not_interested", "do_not_contact"}
# Order a prospect moves through; `sync` only moves forward (except "stop").
PROGRESS = ["new", "queued", "sent", "replied", "call_booked", "client", "not_interested", "do_not_contact"]
# French statuses Saad types in the daily queue sheet -> master status.
SHEET_STATUS = {"envoyé": "sent", "envoye": "sent", "répondu": "replied", "repondu": "replied",
                "appel pris": "call_booked", "client": "client", "pas intéressé": "not_interested",
                "pas interesse": "not_interested", "stop": "do_not_contact"}


def load(path):
    if not os.path.exists(path):
        return {}
    with open(path, newline="", encoding="utf-8") as f:
        return {r["place_id"]: r for r in csv.DictReader(f)}


def save(path, rows, cols=MASTER_COLS):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    os.replace(tmp, path)
