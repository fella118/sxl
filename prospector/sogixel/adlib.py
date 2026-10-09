"""Past and current advertising, from public ad libraries.

Meta: the Ad Library API returns commercial ads only when they reached the EU (kept 1 year after the last
impression). That is exactly the clinics advertising to MRE and medical tourists. Ads shown only in Morocco
are not in the API, so the queue also carries one-click links for a manual check (Meta + Google).
"""
import datetime as dt
import json
import os
import urllib.error
import urllib.parse
import urllib.request

from .scoring import norm

FIELDS = "page_id,page_name,ad_delivery_start_time,ad_delivery_stop_time,ad_snapshot_url"


class AdLibError(RuntimeError):
    pass


def token():
    return os.environ.get("META_ADLIB_TOKEN", "")


def search(term, countries, version="v21.0", pages=2):
    """All ads (active and inactive) mentioning `term` that reached `countries`."""
    params = {"search_terms": term, "ad_reached_countries": json.dumps(countries), "ad_active_status": "ALL",
              "ad_type": "ALL", "fields": FIELDS, "limit": 100, "access_token": token()}
    url = f"https://graph.facebook.com/{version}/ads_archive?" + urllib.parse.urlencode(params)
    ads = []
    for _ in range(pages):
        try:
            with urllib.request.urlopen(url, timeout=30) as r:
                data = json.load(r)
        except urllib.error.HTTPError as e:
            raise AdLibError(f"Ad Library {e.code}: {e.read()[:300].decode(errors='replace')}") from e
        ads += data.get("data", [])
        url = (data.get("paging") or {}).get("next")
        if not url:
            break
    return ads


def _same_page(page_name, name, ig_handle):
    """Is this ad from the clinic's own page? Most of the clinic name's words must appear in the page name."""
    p = norm(page_name).replace(".", " ").replace("_", " ")
    if ig_handle and norm(ig_handle).replace(".", " ").replace("_", " ") in p:
        return True
    words = [w for w in norm(name).split() if len(w) > 2 and w not in {"clinique", "centre", "cabinet", "dentaire",
                                                                         "docteur", "the", "des", "les", "and"}]
    return bool(words) and sum(w in p for w in words) / len(words) >= 0.6


def summarize(ads, name, ig_handle="", today=None):
    """Evidence dict for the clinic's own ads: count, active now, first start, last stop."""
    today = today or dt.date.today().isoformat()
    own = [a for a in ads if _same_page(a.get("page_name", ""), name, ig_handle)]
    if not own:
        return {}
    stops = [a.get("ad_delivery_stop_time", "")[:10] for a in own]
    active = any(not s or s >= today for s in stops)
    return {
        "meta_eu_ads": len(own),
        "meta_eu_active": active,
        "meta_eu_first": min(a.get("ad_delivery_start_time", "")[:10] for a in own),
        "meta_eu_last": "" if active else max(stops),
        "meta_page": own[0].get("page_name", ""),
    }


def meta_evidence(name, ig_handle, cfg):
    """Look the clinic up in the EU ad archive. Empty dict when there's no token or nothing found."""
    if not token():
        return {}
    m = cfg.get("meta", {})
    ads = search(name, m.get("countries", ["FR", "BE", "NL", "ES", "IT", "DE"]), m.get("api_version", "v21.0"))
    return summarize(ads, name, ig_handle)


def describe(site, ads):
    """One readable line of advertising evidence for the queue sheet."""
    out = []
    for key, label in (("meta_pixel", "Pixel Meta"), ("google_ads", "Tag Google Ads"), ("tiktok_pixel", "Pixel TikTok")):
        if site.get(key):
            out.append(label)
        elif site.get(key + "_gtm"):
            out.append(label + " (via Tag Manager)")
    if ads.get("meta_eu_ads"):
        state = "actives" if ads["meta_eu_active"] else f"arrêtées le {ads['meta_eu_last']}"
        out.append(f"{ads['meta_eu_ads']} pubs Meta vers l'Europe depuis le {ads['meta_eu_first']}, {state}")
    return " · ".join(out)


def meta_library_url(name):
    q = urllib.parse.quote(name)
    return ("https://www.facebook.com/ads/library/?active_status=all&ad_type=all&country=ALL"
            f"&q={q}&search_type=keyword_unordered")


def google_transparency_url(website):
    domain = urllib.parse.urlsplit(website if "//" in website else "//" + website).hostname or ""
    domain = domain.removeprefix("www.")
    return f"https://adstransparency.google.com/?region=MA&domain={domain}" if domain else ""
