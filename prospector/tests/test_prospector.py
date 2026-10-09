"""Offline tests (synthetic data, no network). Run from prospector/: python -m unittest -v"""
import csv
import os
import tempfile
import unittest
from unittest import mock

from sogixel import __main__ as cli, adlib, audit, outreach, places, scoring, store

CFG = cli.load_cfg(os.path.join(os.path.dirname(__file__), "..", "config.toml"))

SITE_HTML = """<html><head><meta name="viewport" content="width=device-width">
<script async src="https://connect.facebook.net/en_US/fbevents.js"></script><script>fbq('init','123');</script>
</head><body><a href="https://wa.me/212600000000">WhatsApp</a>
<a href="https://www.instagram.com/clinique.exemple/">IG</a> <a href="https://instagram.com/p/xyz">post</a>
<a href="mailto:contact@clinique-exemple.ma">contact</a> dr.nom@gmail.com logo@2x.png</body></html>"""


def place(**kw):
    p = {"place_id": "pid1", "name": "Clinique Exemple", "types": ["dentist"], "business_status": "OPERATIONAL",
         "website": "https://clinique-exemple.ma", "phone": "+212 5 22 00 00 00", "rating": 4.5,
         "reviews_count": 80, "maps_url": "https://maps.google.com/?cid=1", "reviews": []}
    p.update(kw)
    return p


class AuditTest(unittest.TestCase):
    def test_detects_tools_and_contacts(self):
        a = audit.analyze(SITE_HTML, "https://clinique-exemple.ma/")
        self.assertTrue(a["meta_pixel"] and a["whatsapp"] and a["https"] and a["mobile_ready"])
        self.assertFalse(a["gtm"] or a["booking_tool"] or a["agency_crm"])
        self.assertEqual(a["ig_handle"], "clinique.exemple")
        self.assertEqual(a["email_generic"], "contact@clinique-exemple.ma")
        self.assertEqual(a["emails_named"], 1)   # the personal gmail is counted, never kept

    def test_agency_crm(self):
        self.assertTrue(audit.analyze('<script src="https://widgets.leadconnectorhq.com/x.js">')["agency_crm"])

    def test_no_website(self):
        self.assertEqual(audit.audit("")["audit_note"], "no_website")


class ScoringTest(unittest.TestCase):
    def test_review_pain_languages(self):
        reviews = [{"rating": 1, "text": "Injoignable, personne ne répond au téléphone"},
                   {"rating": 2, "text": "Sent 3 messages, never replied"},
                   {"rating": 2, "text": "ma kayjawbouch f whatsapp"},
                   {"rating": 3, "text": "Beaucoup d'attente"},
                   {"rating": 5, "text": "Ne répond pas vite mais top"}]       # 5 stars: ignored
        strong, weak = scoring.review_pain(reviews)
        self.assertEqual((len(strong), weak), (3, 1))

    def test_hot_when_pain_and_no_tracking(self):
        site = {"audited": True, "meta_pixel": False, "gtm": False, "booking_tool": False, "whatsapp": False}
        s = scoring.score(place(reviews=[{"rating": 1, "text": "Aucune réponse sur WhatsApp"}]), site, CFG, "Casablanca")
        self.assertEqual(s["tier"], "Hot")
        self.assertEqual(s["angle"], "pain_review")

    def test_equipped_clinic_with_agency_is_cold(self):
        site = {"audited": True, "meta_pixel": True, "gtm": True, "booking_tool": True, "whatsapp": True,
                "agency_crm": True}
        self.assertEqual(scoring.score(place(), site, CFG, "Fès")["tier"], "Cold")

    def test_closed(self):
        self.assertEqual(scoring.score(place(business_status="CLOSED_PERMANENTLY"), {}, CFG)["tier"], "Out")

    def test_vertical_match(self):
        self.assertEqual(scoring.match_vertical(place(name="Centre Greffe Capillaire", types=[]), CFG["verticals"]), "hair")
        self.assertIsNone(scoring.match_vertical(place(name="Pharmacie du Centre", types=["pharmacy"]), CFG["verticals"]))


class OutreachTest(unittest.TestCase):
    def test_every_angle_renders(self):
        for angle in outreach.DM:
            s = {"angle": angle, "flags": ["no_whatsapp"], "reasons": [], "pain_quotes": ["x"]}
            m = outreach.render(place(), {}, s, "dental")
            self.assertIn("Clinique Exemple", m["dm"] + m["email_subject"])
            self.assertNotIn("{", m["dm"])
            self.assertIn("stop", m["email_body"])
            self.assertLess(len(m["dm"]), 600)


class PlacesTest(unittest.TestCase):
    def test_normalize(self):
        raw = {"id": "abc", "displayName": {"text": "Clinique Exemple"}, "userRatingCount": 12,
               "reviews": [{"rating": 1, "originalText": {"text": "Injoignable"}, "relativePublishTimeDescription": "il y a 2 mois"}]}
        p = places.normalize(raw)
        self.assertEqual((p["place_id"], p["name"], p["reviews_count"]), ("abc", "Clinique Exemple", 12))
        self.assertEqual(p["reviews"][0]["text"], "Injoignable")


class DailyPipelineTest(unittest.TestCase):
    """Runs `daily` end to end with Places and the site audit stubbed out."""

    def test_daily_builds_queue_and_respects_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            master = os.path.join(tmp, "prospects.csv")
            base = dict(vertical="dental", city="Casablanca", score="70", tier="Hot", angle="", flags="",
                        ig_handle="", email_generic="", first_seen="", last_checked="", last_queued="", notes="", maps_link="")
            store.save(master, [dict(base, place_id="a", status="new", ig_handle="clinique.a"),
                                dict(base, place_id="b", status="new", email_generic="contact@b.ma"),
                                dict(base, place_id="c", status="do_not_contact", ig_handle="clinique.c")])
            pain = [{"rating": 1, "text": "Personne ne répond"}]
            fake = {pid: place(place_id=pid, name=f"Clinique {pid.upper()}", reviews=pain) for pid in "abc"}
            bare = {"audited": True, "meta_pixel": False, "gtm": False, "booking_tool": False, "whatsapp": False}
            with mock.patch.object(places, "details", lambda pid, lang="fr": fake[pid]), \
                 mock.patch.object(audit, "audit", lambda url: bare):
                cli.main(["daily", "--master", master, "--out", tmp, "--date", "2026-10-09"])
            with open(os.path.join(tmp, "2026-10-09", "queue.csv"), encoding="utf-8") as f:
                q = list(csv.DictReader(f))
            self.assertEqual([(r["place_id"], r["channel"]) for r in q], [("a", "dm"), ("b", "email")])
            self.assertEqual(q[0]["instagram_url"], "https://www.instagram.com/clinique.a/")
            rows = store.load(master)
            self.assertEqual((rows["a"]["status"], rows["c"]["status"]), ("queued", "do_not_contact"))
            self.assertTrue(os.path.exists(os.path.join(tmp, "2026-10-09", "report.md")))


class AdsTest(unittest.TestCase):
    def test_gtm_container_reveals_hidden_tags(self):
        js = 'var data={"resource":{"tags":[{"function":"__awct","vtp_conversionId":"123456789"},' \
             '{"function":"__html","vtp_html":"<script>!function(f){f.fbq=1}(window);fbq(\'init\',\'1\')</script>"}]}}'
        self.assertEqual(audit.analyze_gtm(js), {"meta_pixel": True, "google_ads": True, "tiktok_pixel": False})
        self.assertEqual(audit.analyze_gtm("var data={}"), {"meta_pixel": False, "google_ads": False, "tiktok_pixel": False})

    def test_summarize_keeps_only_the_clinics_own_page(self):
        ads = [{"page_name": "Clinique Dentaire Al Amal", "ad_delivery_start_time": "2025-11-02",
                "ad_delivery_stop_time": "2026-04-30"},
               {"page_name": "Al Amal Dental Clinic", "ad_delivery_start_time": "2026-01-10",
                "ad_delivery_stop_time": "2026-05-02"},
               {"page_name": "Some Turkish Hair Clinic", "ad_delivery_start_time": "2026-06-01"}]
        e = adlib.summarize(ads, "Clinique Dentaire Al Amal", today="2026-10-09")
        self.assertEqual((e["meta_eu_ads"], e["meta_eu_active"], e["meta_eu_first"], e["meta_eu_last"]),
                         (2, False, "2025-11-02", "2026-05-02"))
        self.assertTrue(adlib.summarize(ads[2:], "Turkish Hair Clinic", today="2026-10-09")["meta_eu_active"])
        self.assertEqual(adlib.summarize(ads, "Centre Esthétique Rabat Agdal"), {})

    def test_stopped_ads_become_the_angle(self):
        site = {"audited": True, "meta_pixel": True, "gtm": True, "booking_tool": True, "whatsapp": True}
        ads = {"meta_eu_ads": 4, "meta_eu_active": False, "meta_eu_first": "2025-11-02", "meta_eu_last": "2026-05-02"}
        s = scoring.score(place(), site, CFG, "Casablanca", ads)
        self.assertEqual(s["angle"], "ads_stopped")
        self.assertIn("ads_tags", s["flags"])
        m = outreach.render(place(), site, s, "dental")
        self.assertIn("jusqu'au 2 mai 2026", m["dm"])
        self.assertIn("4 pubs Meta vers l'Europe", adlib.describe(site, ads))

    def test_pixel_via_gtm_is_not_no_tracking(self):
        site = {"audited": True, "gtm": True, "meta_pixel_gtm": True, "booking_tool": True, "whatsapp": True}
        s = scoring.score(place(), site, CFG, "Rabat")
        self.assertNotIn("no_tracking", s["flags"])
        self.assertEqual(adlib.describe(site, {}), "Pixel Meta (via Tag Manager)")

    def test_links(self):
        self.assertEqual(adlib.google_transparency_url("https://www.clinique-exemple.ma/fr/"),
                         "https://adstransparency.google.com/?region=MA&domain=clinique-exemple.ma")
        self.assertEqual(adlib.google_transparency_url(""), "")
        self.assertIn("active_status=all", adlib.meta_library_url("Clinique Exemple"))


class SyncTest(unittest.TestCase):
    def test_sheet_statuses_flow_back(self):
        with tempfile.TemporaryDirectory() as tmp:
            master, queue = os.path.join(tmp, "m.csv"), os.path.join(tmp, "q.csv")
            store.save(master, [{"place_id": "a", "status": "queued", "score": "70"},
                                {"place_id": "b", "status": "replied", "score": "60"},
                                {"place_id": "c", "status": "queued", "score": "50"}])
            store.save(queue, [{"place_id": "a", "status": "Envoyé"}, {"place_id": "b", "status": "envoyé"},
                               {"place_id": "c", "status": "stop"}], store.QUEUE_COLS)
            cli.main(["sync", queue, "--master", master])
            rows = store.load(master)
            self.assertEqual([rows[k]["status"] for k in "abc"], ["sent", "replied", "do_not_contact"])


if __name__ == "__main__":
    unittest.main()
