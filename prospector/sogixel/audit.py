"""Polite audit of a clinic's own website: one homepage request, robots.txt respected.

Finds what the owner already has (tracking, booking, WhatsApp, CRM) and the public
contact points they published themselves (Instagram, generic email).
"""
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser

UA = "Mozilla/5.0 (compatible; SOGIXEL-audit/1.0)"

PATTERNS = {
    "meta_pixel": r"connect\.facebook\.net/[^\"']*fbevents\.js|fbq\(\s*['\"]init",
    "gtm": r"googletagmanager\.com/gtm\.js|\bGTM-[A-Z0-9]{4,}",
    "ga4": r"googletagmanager\.com/gtag/js\?id=G-|['\"]G-[A-Z0-9]{6,}['\"]",
    "google_ads": r"\bAW-\d{6,}",
    "tiktok_pixel": r"analytics\.tiktok\.com|ttq\.load",
    "whatsapp": r"wa\.me/|api\.whatsapp\.com/send|whatsapp://send|web\.whatsapp\.com/send",
    "booking_tool": r"calendly\.com|dabadoc|doctolib|booksy|fresha\.com|setmore|simplybook|"
                    r"acuityscheduling|cal\.com/|zcal\.co|youcanbook\.me|tidycal",
    # Someone (often an agency) already runs a CRM / funnel stack for them.
    "agency_crm": r"leadconnectorhq|msgsndr\.com|gohighlevel|hs-scripts\.com|hubspot|zohocrm|kommo\.com|amocrm",
    "chat_widget": r"tawk\.to|crisp\.chat|intercom|livechatinc|tidio|manychat",
}
_IG = re.compile(r"instagram\.com/([A-Za-z0-9_.]{2,30})", re.I)
_IG_SKIP = {"p", "reel", "reels", "explore", "accounts", "stories", "tv", "share", "about",
            "developer", "legal", "direct", "web"}
_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,10}")
_EMAIL_JUNK = (".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", "sentry", "wixpress", "example.",
               "domain.com", "email.com")
# Role addresses belong to the business, not to a person (Loi 09-08 is about natural persons).
GENERIC_LOCAL = ("contact", "info", "rdv", "rendezvous", "rendez-vous", "accueil", "secretariat",
                 "hello", "bonjour", "admin", "reception", "booking", "office", "clinique",
                 "cabinet", "centre", "service", "support", "direction")


def _robots_allows(url):
    parts = urllib.parse.urlsplit(url)
    rp = urllib.robotparser.RobotFileParser()
    try:
        req = urllib.request.Request(f"{parts.scheme}://{parts.netloc}/robots.txt", headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=8) as r:
            rp.parse(r.read(200_000).decode("utf-8", "replace").splitlines())
    except Exception:
        return True                      # no robots.txt (or unreachable) -> allowed
    return rp.can_fetch(UA, url)


def fetch(url, timeout=12, max_bytes=1_500_000):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "fr,en;q=0.8"})
    t0 = time.monotonic()
    with urllib.request.urlopen(req, timeout=timeout) as r:
        body = r.read(max_bytes)
        charset = r.headers.get_content_charset() or "utf-8"
        return r.geturl(), body.decode(charset, "replace"), round(time.monotonic() - t0, 2)


def analyze(html, final_url=""):
    """Pure function: findings from a page's HTML."""
    found = {k: bool(re.search(p, html, re.I)) for k, p in PATTERNS.items()}
    handles = [h for h in _IG.findall(html) if h.lower() not in _IG_SKIP]
    emails = sorted({e.lower() for e in _EMAIL.findall(html) if not any(j in e.lower() for j in _EMAIL_JUNK)})
    generic = [e for e in emails if e.split("@")[0].startswith(GENERIC_LOCAL)]
    found.update({
        "ig_handle": handles[0].rstrip(".") if handles else "",
        "email_generic": generic[0] if generic else "",
        "emails_named": len(emails) - len(generic),   # counted, never stored or contacted
        "https": final_url.startswith("https://"),
        "mobile_ready": bool(re.search(r"<meta[^>]+name=[\"']viewport", html, re.I)),
    })
    return found


# Inside a Tag Manager container: pixels and ad tags that never appear in the page HTML.
GTM_PATTERNS = {
    "meta_pixel": r"fbevents\.js|connect\.facebook\.net|fbq\(",
    "google_ads": r"AW-\d{6,}|__awct|vtp_conversionId|googleadservices",
    "tiktok_pixel": r"analytics\.tiktok\.com",
}
_GTM_ID = re.compile(r"\bGTM-[A-Z0-9]{4,9}\b")


def analyze_gtm(js):
    return {k: bool(re.search(p, js)) for k, p in GTM_PATTERNS.items()}


def scan_gtm(html):
    """Fetch the site's public GTM container(s) and report the ad tags configured inside."""
    found = {}
    for gid in list(dict.fromkeys(_GTM_ID.findall(html)))[:2]:
        try:
            _, js, _ = fetch(f"https://www.googletagmanager.com/gtm.js?id={gid}", max_bytes=3_000_000)
        except (urllib.error.URLError, TimeoutError, ConnectionError, ValueError):
            continue
        for k, v in analyze_gtm(js).items():
            found[k] = found.get(k) or v
    return {f"{k}_gtm": v for k, v in found.items()}


def audit(url):
    if not url:
        return {"audited": False, "audit_note": "no_website"}
    if not re.match(r"https?://", url):
        url = "http://" + url
    if not _robots_allows(url):
        return {"audited": False, "audit_note": "robots_disallow"}
    try:
        final, html, secs = fetch(url)
    except (urllib.error.URLError, TimeoutError, ConnectionError, ValueError) as e:
        return {"audited": False, "audit_note": f"unreachable: {type(e).__name__}"}
    out = analyze(html, final)
    if out["gtm"]:
        out.update(scan_gtm(html))
    out.update({"audited": True, "audit_note": "", "load_s": secs})
    return out
