"""First-touch messages. One true finding, one question, no link, Saad's voice ("vous", calm).

These are the fallback drafts; the daily Claude run rewrites each one from the `facts`
column only, so nothing in a message can be invented.
"""
V_SHORT = {"aesthetic": "esthétiques", "hair": "de greffe capillaire", "dental": "dentaires"}
HELLO = "Bonjour, je suis Saad, fondateur de SOGIXEL. "

DM = {
    "pain_review": "En lisant les avis de {name}, {pain_phrase}. Dans une clinique {v}, une demande sans "
                   "réponse part souvent chez le concurrent. On installe un assistant qui répond en quelques "
                   "secondes, même à 21h, et qui fixe le rendez-vous. Je vous montre en 10 minutes comment ça "
                   "marcherait chez vous ?",
    "ads_stopped": "J'ai vu dans la bibliothèque publicitaire de Meta que {name} a diffusé des publicités vers "
                   "l'Europe jusqu'au {last}, puis plus rien. Souvent, on coupe parce qu'on ne voit pas combien de "
                   "patients la pub ramène vraiment. On installe le suivi qui le montre, et un assistant qui répond "
                   "aux demandes en quelques secondes. Je vous montre en 10 minutes ?",
    "meta_eu": "J'ai vu les publicités Meta de {name} qui tournent en ce moment vers l'Europe. Les patients de la "
               "diaspora écrivent souvent le soir et contactent plusieurs cliniques à la fois : celle qui répond la "
               "première prend souvent le rendez-vous. On installe un assistant qui répond en quelques secondes, en "
               "français ou en anglais. Je vous montre comment ?",
    "no_tracking": "J'ai regardé le site de {name} : il n'y a ni pixel Meta ni tag Google Ads. Si vous faites de la "
                   "publicité sur Instagram, Facebook ou Google, impossible de savoir combien vous coûte un patient, "
                   "ni quelle pub ramène des rendez-vous. Je peux vous montrer ce qu'on mesure pour nos clients, en "
                   "10 minutes ?",
    "no_booking": "Sur le site de {name}, je n'ai trouvé ni prise de rendez-vous en ligne{wa}. Le soir et le "
                  "week-end, c'est souvent là que vos futurs patients se décident, et personne ne leur répond. "
                  "On met en place un assistant qui répond et fixe le RDV, 24h/24. Je vous montre comment ?",
    "no_whatsapp": "Sur le site de {name}, il n'y a pas de bouton WhatsApp. Au Maroc, c'est le premier réflexe "
                   "d'un patient qui hésite : une question, une réponse rapide, et le rendez-vous est pris. On "
                   "installe ça avec un assistant qui répond même à 21h. Je vous montre en 10 minutes ?",
    "new_opening": "J'ai vu que {name} a encore peu d'avis sur Google Maps. C'est souvent la période où "
                   "l'agenda se remplit, ou pas. On aide les cliniques {v} à démarrer avec un vrai système "
                   "patients : pub mesurée, réponse WhatsApp automatique, relances et rappels de RDV. Je vous "
                   "explique comment en 10 minutes ?",
    "no_site": "Vos futurs patients trouvent {name} sur Google Maps, mais il n'y a ni site ni prise de "
               "rendez-vous derrière. Ils comparent, et réservent souvent là où c'est le plus simple. On met en "
               "place une page, un WhatsApp qui répond 24h/24 et le suivi des RDV. Je vous montre en 10 minutes ?",
    "generic": "On aide les cliniques {v} au Maroc à transformer leurs demandes en rendez-vous : réponse WhatsApp "
               "en quelques secondes, relances automatiques, et un rapport clair sur ce que rapporte chaque "
               "dirham de pub. Remplir l'agenda, c'est un sujet pour {name} en ce moment ?",
}
SUBJECT = {
    "pain_review": "Les messages sans réponse de {name}",
    "ads_stopped": "Les pubs de {name} vers l'Europe",
    "meta_eu": "Les patients d'Europe de {name}",
    "no_tracking": "{name} : combien vous coûte un patient ?",
    "no_booking": "Les demandes du soir chez {name}",
    "no_whatsapp": "Les demandes du soir chez {name}",
    "new_opening": "Remplir l'agenda de {name}",
    "no_site": "{name} sur Google Maps",
    "generic": "Une idée pour l'agenda de {name}",
}
CALL = {
    "pain_review": "plusieurs avis Google parlent de messages restés sans réponse",
    "ads_stopped": "vos publicités Meta vers l'Europe se sont arrêtées et je voulais comprendre pourquoi",
    "meta_eu": "j'ai vu vos publicités vers l'Europe et les patients de la diaspora écrivent souvent le soir",
    "no_tracking": "votre site n'a aucun tag publicitaire, donc impossible de mesurer ce que rapporte la pub",
    "no_booking": "vos patients ne peuvent pas prendre rendez-vous en ligne le soir",
    "no_whatsapp": "il n'y a pas de bouton WhatsApp sur votre site",
    "new_opening": "votre clinique est récente sur Google Maps",
    "no_site": "vos patients vous trouvent sur Maps mais n'ont pas de site pour réserver",
    "generic": "on aide les cliniques à transformer leurs demandes en rendez-vous",
}
OPT_OUT = "Si ce n'est pas le bon moment, répondez « stop » et je ne vous écrirai plus."


def facts(place, site, scored):
    """Only verifiable facts. The daily Claude rewrite may use these and nothing else."""
    f = [f"Nom : {place['name']}", f"Ville : {place.get('city', '')}"]
    f += scored["reasons"]
    f += [f"Avis cité : « {q} »" for q in scored.get("pain_quotes", [])[:2]]
    if site.get("audited"):
        tools = ", ".join(k for k in ("meta_pixel", "meta_pixel_gtm", "gtm", "ga4", "google_ads", "google_ads_gtm",
                                      "booking_tool", "whatsapp", "chat_widget") if site.get(k))
        f.append(f"Outils sur le site : {tools or 'aucun détecté'}")
    return " | ".join(f)


def render(place, site, scored, vertical):
    n = len(scored.get("pain_quotes", []))
    pain_phrase = ("un patient explique ne pas avoir eu de réponse à son message ou son appel" if n == 1 else
                   "plusieurs patients expliquent ne pas avoir eu de réponse à leurs messages ou appels")
    ctx = {"name": place["name"], "v": V_SHORT.get(vertical, ""), "pain_phrase": pain_phrase,
           "wa": " ni bouton WhatsApp" if "no_whatsapp" in scored["flags"] else "",
           "last": fr_date(scored.get("ads", {}).get("meta_eu_last", ""))}
    angle = scored["angle"] if scored["angle"] in DM else "generic"
    dm = HELLO + DM[angle].format(**ctx)
    return {
        "dm": dm,
        "email_subject": SUBJECT[angle].format(**ctx),
        "email_body": f"{dm}\n\nSaad\nSOGIXEL\n\n{OPT_OUT}",
        "call_opener": f"Bonjour, Saad de SOGIXEL. Je vous appelle parce que {CALL[angle]}. Vous avez deux minutes ?",
    }


MONTHS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre",
          "novembre", "décembre"]


def fr_date(iso):
    """'2026-05-02' -> '2 mai 2026'."""
    try:
        y, m, d = (int(x) for x in iso[:10].split("-"))
        return f"{d} {MONTHS[m - 1]} {y}"
    except ValueError:
        return iso
