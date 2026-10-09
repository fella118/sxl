"""Fit + pain scoring. Transparent on purpose: every point comes with a reason Saad can read."""
import unicodedata

# Bad reviews that prove lost patients: nobody answers, nobody calls back.
STRONG_PAIN = (
    "injoignable", "ne repond", "repondent pas", "repond pas", "pas de reponse", "aucune reponse",
    "jamais repondu", "personne ne repond", "jamais rappele", "pas rappele", "aucun retour",
    "no answer", "never answer", "never replied", "no reply", "didn't reply", "did not reply",
    "unreachable", "no response", "hard to reach", "couldn't reach", "could not reach",
    "ma kayjawbouch", "makayjawbouch", "ma jawbouch", "ما كيجاوبوش", "لا يجيبون", "لا أحد يجيب", "ماكيجاوبوش",
)
# Weaker signals: organisation problems rather than lost demand.
WEAK_PAIN = ("attente", "attendu", "retard", "desorganis", "accueil", "waiting", "waited", "rude", "انتظار")


def norm(s):
    s = unicodedata.normalize("NFKD", (s or "").lower())
    return "".join(c for c in s if not unicodedata.combining(c))


def match_vertical(place, verticals):
    hay = norm(place.get("name", "") + " " + " ".join(place.get("types", [])))
    for v in verticals:
        if any(norm(m) in hay for m in v["match"]) or set(v.get("types", [])) & set(place.get("types", [])):
            return v["key"]
    return None


def review_pain(reviews):
    """(strong quotes, weak count) from reviews rated 3 stars or less."""
    strong, weak = [], 0
    for r in reviews or []:
        if (r.get("rating") or 5) > 3:
            continue
        t = norm(r.get("text", ""))
        if any(k in t for k in map(norm, STRONG_PAIN)):
            strong.append(r.get("text", "").strip().replace("\n", " ")[:160])
        elif any(k in t for k in map(norm, WEAK_PAIN)):
            weak += 1
    return strong, weak


def score(place, site, cfg, city=""):
    """Return {score, tier, angle, reasons, flags}. `site` is the audit result."""
    pts, reasons, flags = 10, ["Vertical high-ticket"], []
    n, rating = place.get("reviews_count", 0), place.get("rating") or 0

    if place.get("business_status") not in ("", "OPERATIONAL"):
        return {"score": 0, "tier": "Out", "angle": "closed", "reasons": ["Établissement fermé"], "flags": ["closed"]}

    # Fit: can they pay, are they worth it now?
    if rating >= 4.2 and n >= 40:
        pts += 10; reasons.append(f"Établi : {rating}★ / {n} avis"); flags.append("established")
    elif n >= 15:
        pts += 5; reasons.append(f"{n} avis Google")
    elif n < 10:
        pts += 8; reasons.append(f"Ouverture récente probable ({n} avis)"); flags.append("new_opening")
    if city in cfg["market"]["tier1_cities"]:
        pts += 5

    # Pain: things we fix.
    strong, weak = review_pain(place.get("reviews"))
    if strong:
        pts += min(30, 15 * len(strong)); flags.append("pain_review")
        reasons.append(f"{len(strong)} avis : patients sans réponse")
    if weak:
        pts += min(10, 5 * weak); reasons.append(f"{weak} avis : attente / accueil")

    if not place.get("website"):
        pts += 6; flags.append("no_site"); reasons.append("Pas de site : tout passe par Maps / Instagram")
    elif site.get("audited"):
        if not site.get("meta_pixel") and not site.get("gtm"):
            pts += 18; flags.append("no_tracking"); reasons.append("Site sans pixel Meta ni Tag Manager")
        if not site.get("booking_tool"):
            pts += 10; flags.append("no_booking"); reasons.append("Pas de prise de RDV en ligne")
        if not site.get("whatsapp"):
            pts += 8; flags.append("no_whatsapp"); reasons.append("Pas de bouton WhatsApp")
        if site.get("agency_crm"):
            pts -= 20; flags.append("has_agency"); reasons.append("CRM d'agence déjà installé (−)")

    pts = max(0, min(100, pts))
    s = cfg["scoring"]
    tier = "Hot" if pts >= s["hot"] else "Warm" if pts >= s["warm"] else "Cold"
    angle = next((a for a in ("pain_review", "no_tracking", "no_booking", "no_whatsapp", "new_opening", "no_site")
                  if a in flags), "generic")
    return {"score": pts, "tier": tier, "angle": angle, "reasons": reasons, "flags": flags,
            "pain_quotes": strong}
