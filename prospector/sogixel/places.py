"""Google Places API (New) client.

Google Maps Platform terms only allow storing place IDs long-term, so the master
list keeps the ID plus our own findings, and everything else (name, phone,
reviews...) is fetched fresh on the day it is needed.
"""
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

BASE = "https://places.googleapis.com/v1"
_FIELDS = ("id", "displayName", "primaryType", "types", "businessStatus", "formattedAddress",
           "websiteUri", "nationalPhoneNumber", "internationalPhoneNumber", "rating",
           "userRatingCount", "googleMapsUri", "reviews")
SEARCH_MASK = ",".join("places." + f for f in _FIELDS) + ",nextPageToken"
DETAILS_MASK = ",".join(_FIELDS)


class PlacesError(RuntimeError):
    pass


def _key():
    key = os.environ.get("GOOGLE_PLACES_API_KEY")
    if not key:
        raise PlacesError("GOOGLE_PLACES_API_KEY is not set (add it in the environment settings)")
    return key


def _call(method, url, mask, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={
        "Content-Type": "application/json", "X-Goog-Api-Key": _key(), "X-Goog-FieldMask": mask})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.load(resp)
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 503) and attempt < 3:
                time.sleep(2 ** (attempt + 1))
                continue
            raise PlacesError(f"Places API {e.code}: {e.read()[:300].decode(errors='replace')}") from e


def search(query, language="fr", region="MA", max_pages=3):
    """Yield normalized places for a text query, following pagination."""
    token = None
    for _ in range(max_pages):
        body = {"textQuery": query, "languageCode": language, "regionCode": region, "pageSize": 20}
        if token:
            body["pageToken"] = token
        data = _call("POST", f"{BASE}/places:searchText", SEARCH_MASK, body)
        for p in data.get("places", []):
            yield normalize(p)
        token = data.get("nextPageToken")
        if not token:
            break


def details(place_id, language="fr"):
    url = f"{BASE}/places/{urllib.parse.quote(place_id)}?languageCode={language}"
    return normalize(_call("GET", url, DETAILS_MASK))


def normalize(p):
    def text(obj):
        return (obj or {}).get("text") or ""
    return {
        "place_id": p["id"],
        "name": text(p.get("displayName")),
        "types": p.get("types", []),
        "business_status": p.get("businessStatus", ""),
        "address": p.get("formattedAddress", ""),
        "website": p.get("websiteUri", ""),
        "phone": p.get("internationalPhoneNumber") or p.get("nationalPhoneNumber", ""),
        "rating": p.get("rating"),
        "reviews_count": p.get("userRatingCount", 0) or 0,
        "maps_url": p.get("googleMapsUri", ""),
        "reviews": [{"rating": r.get("rating"),
                     "text": text(r.get("originalText")) or text(r.get("text")),
                     "when": r.get("relativePublishTimeDescription", "")}
                    for r in p.get("reviews", [])],
    }


def maps_link(place_id):
    """A Maps link built from the place ID alone (safe to store)."""
    return f"https://www.google.com/maps/place/?q=place_id:{place_id}"
