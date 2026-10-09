"""`python -m sogixel check [--live]`: is everything configured? With --live, each service is actually called once."""
import datetime as dt
import os
import tempfile
from zoneinfo import ZoneInfo

REQUIRED = [("ANTHROPIC_API_KEY", "Claude: the setter and the morning polish"),
            ("GHL_TOKEN", "GoHighLevel API"), ("GHL_LOCATION_ID", "GoHighLevel sub-account"),
            ("GHL_CALENDAR_ID", "calendar for booked calls"), ("GHL_OWNER_CONTACT_ID", "your notifications"),
            ("PUBLIC_URL", "cockpit link in the morning message"), ("GOOGLE_PLACES_API_KEY", "finding clinics")]
OPTIONAL = [("META_ADLIB_TOKEN", "past Meta ads to Europe")]


def run(cfg, data_dir, live=False):
    ok = True

    def line(good, label, detail=""):
        nonlocal ok
        mark = {True: "✓", False: "✗", None: "–"}[good]
        ok = ok and good is not False
        print(f" {mark} {label}" + (f"  ({detail})" if detail else ""))

    print("Configuration")
    for k, why in REQUIRED:
        line(bool(os.environ.get(k)), k, why if not os.environ.get(k) else "")
    for k, why in OPTIONAL:
        line(True if os.environ.get(k) else None, k, "" if os.environ.get(k) else f"optional: {why}")
    for k in ("COCKPIT_KEY", "WEBHOOK_KEY"):
        v = os.environ.get(k) or os.environ.get("EMPLOYEE_KEY", "")
        line(len(v) >= 24, k, "" if len(v) >= 24 else "set it (or EMPLOYEE_KEY) to 24+ random characters")
    mode = os.environ.get("SETTER_MODE", "shadow")
    line(mode in ("shadow", "live"), f"SETTER_MODE={mode}",
         "replies go to you as drafts" if mode == "shadow" else "replies go to prospects")
    e = cfg["employee"]
    try:
        ZoneInfo(e["timezone"])
        line(True, f"timezone {e['timezone']}", f"now {dt.datetime.now(ZoneInfo(e['timezone'])):%H:%M}")
    except Exception as ex:                                  # noqa: BLE001 - report, don't crash the check
        line(False, "timezone", str(ex))
    try:
        os.makedirs(data_dir, exist_ok=True)
        tempfile.TemporaryFile(dir=data_dir).close()
        line(True, f"data dir {data_dir} writable")
    except OSError as ex:
        line(False, f"data dir {data_dir}", str(ex))

    if live:
        print("Live checks")
        _live(cfg, line)
    print("\nAll good." if ok else "\nFix the ✗ lines, then run this again.")
    return 0 if ok else 1


def _live(cfg, line):
    from . import adlib, places
    from .ghl import GHL

    def probe(label, fn):
        try:
            line(True, label, fn() or "")
        except Exception as ex:                              # noqa: BLE001 - every failure is reported
            line(False, label, f"{type(ex).__name__}: {str(ex)[:160]}")

    ghl, e = GHL(), cfg["employee"]
    probe("GoHighLevel: your contact", lambda: ghl.contact(os.environ["GHL_OWNER_CONTACT_ID"]).get("firstName", ""))

    def slots():
        now = dt.datetime.now(ZoneInfo(e["timezone"]))
        s = ghl.free_slots(os.environ["GHL_CALENDAR_ID"], int(now.timestamp() * 1000),
                           int((now + dt.timedelta(days=7)).timestamp() * 1000), e["timezone"])
        if not s:
            raise RuntimeError("no free slot in the next 7 days: check the calendar's availability")
        return f"{len(s)} free slots this week"
    probe("GoHighLevel: calendar", slots)

    def claude():
        import anthropic
        m = anthropic.Anthropic().models.retrieve(e["model"])
        return m.id
    probe("Claude API", claude)
    probe("Google Places", lambda: next(places.search("clinique dentaire Casablanca", max_pages=1))["name"])
    if adlib.token():
        probe("Meta Ad Library", lambda: f"{len(adlib.search('clinique', ['FR'], cfg['meta']['api_version'], pages=1))} ads")
