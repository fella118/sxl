"""SOGIXEL prospector.

  python -m sogixel pull     # one-off (then monthly): find every target clinic, audit, score
  python -m sogixel daily    # every morning: refresh the best prospects, build today's queue + report
  python -m sogixel sync out/*/queue.csv   # pull the statuses Saad set in the queue sheets back into the master
  python -m sogixel stats    # what's in the master list
"""
import argparse
import datetime as dt
import os
import sys
import tomllib
from concurrent.futures import ThreadPoolExecutor

from . import adlib, audit, outreach, places, scoring, store

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_cfg(path):
    with open(path, "rb") as f:
        return tomllib.load(f)


def _audit_all(found):
    with ThreadPoolExecutor(max_workers=8) as ex:
        return list(ex.map(lambda p: audit.audit(p.get("website", "")), found))


def cmd_pull(cfg, args):
    master = store.load(args.master)
    today = dt.date.today().isoformat()
    verticals = [v for v in cfg["verticals"] if not args.verticals or v["key"] in args.verticals]
    cities = args.cities or cfg["market"]["cities"]
    seen, found = set(master), []
    for v in verticals:
        for city in cities:
            for q in v["queries"]:
                for p in places.search(f"{q} {city}", cfg["market"]["language"], cfg["market"]["region"],
                                       cfg["market"]["pages_per_query"]):
                    if p["place_id"] in seen:
                        continue
                    seen.add(p["place_id"])
                    # Keep it only if it really is one of our verticals (search also returns pharmacies, salons...).
                    vk = scoring.match_vertical(p, [v]) or scoring.match_vertical(p, cfg["verticals"])
                    if vk:
                        p["vertical"], p["city"] = vk, city
                        found.append(p)
            print(f"  {v['key']:<9} {city:<11} -> {len(found)} new so far", flush=True)
    sites = _audit_all(found)
    for p, site in zip(found, sites):
        s = scoring.score(p, site, cfg, p["city"])
        master[p["place_id"]] = {
            "place_id": p["place_id"], "vertical": p["vertical"], "city": p["city"], "score": s["score"],
            "tier": s["tier"], "angle": s["angle"], "flags": " ".join(s["flags"]),
            "ads_evidence": adlib.describe(site, {}), "ig_handle": site.get("ig_handle", ""), "email_generic": site.get("email_generic", ""),
            "status": "new", "first_seen": today, "last_checked": today, "last_queued": "", "notes": "",
            "maps_link": places.maps_link(p["place_id"]),
        }
    store.save(args.master, sorted(master.values(), key=lambda r: -int(r["score"] or 0)))
    tiers = [master[p["place_id"]]["tier"] for p in found]
    print(f"Added {len(found)} prospects: {tiers.count('Hot')} Hot, {tiers.count('Warm')} Warm, "
          f"{tiers.count('Cold')} Cold -> {args.master}")


def cmd_daily(cfg, args):
    master = store.load(args.master)
    if not master:
        sys.exit("Master list is empty: run `python -m sogixel pull` first.")
    day = args.date or dt.date.today().isoformat()
    d = cfg["daily"]
    pool = sorted((r for r in master.values() if r["status"] in store.OPEN and r["tier"] in ("Hot", "Warm")),
                  key=lambda r: -int(r["score"] or 0))[:d["candidates"]]

    fresh = []
    for r in pool:
        try:
            fresh.append(places.details(r["place_id"], cfg["market"]["language"]))
        except places.PlacesError as e:          # e.g. listing removed from Maps
            r["notes"] = f"{day}: details failed ({str(e)[:60]})"
            fresh.append(None)
    pool = [r for r, p in zip(pool, fresh) if p]
    fresh = [p for p in fresh if p]
    sites = _audit_all(fresh)
    if not adlib.token():
        print("META_ADLIB_TOKEN not set: skipping the Meta ad-history check (links still added)")
    quotas = {"dm": d["dm_quota"], "email": d["email_quota"], "call": d["call_quota"]}
    queue = []
    for row, p, site in zip(pool, fresh, sites):
        p["city"] = row["city"]
        try:
            ads = adlib.meta_evidence(p["name"], site.get("ig_handle") or row["ig_handle"], cfg)
        except adlib.AdLibError as e:
            ads, row["notes"] = {}, f"{day}: ad library failed ({str(e)[:60]})"
        s = scoring.score(p, site, cfg, row["city"], ads)
        evidence = adlib.describe(site, ads)
        row.update(score=s["score"], tier=s["tier"], angle=s["angle"], flags=" ".join(s["flags"]), ads_evidence=evidence,
                   ig_handle=site.get("ig_handle") or row["ig_handle"],
                   email_generic=site.get("email_generic") or row["email_generic"], last_checked=day)
        if s["tier"] not in ("Hot", "Warm"):
            continue
        channel = ("dm" if row["ig_handle"] and quotas["dm"] else
                   "email" if row["email_generic"] and quotas["email"] else
                   "call" if p["phone"] and quotas["call"] else None)
        if not channel:
            continue
        quotas[channel] -= 1
        msg = outreach.render(p, site, s, row["vertical"])
        queue.append({
            "date": day, "channel": channel, "tier": s["tier"], "score": s["score"], "vertical": row["vertical"],
            "city": row["city"], "name": p["name"],
            "instagram_url": f"https://www.instagram.com/{row['ig_handle']}/" if row["ig_handle"] else "",
            "email": row["email_generic"], "phone": p["phone"], "maps_url": p["maps_url"], "website": p["website"],
            "ads_evidence": evidence, "ad_library_url": adlib.meta_library_url(p["name"]),
            "google_ads_url": adlib.google_transparency_url(p["website"]), "reasons": " · ".join(s["reasons"]),
            "facts": outreach.facts(p, site, s), **msg, "place_id": p["place_id"], "status": "à envoyer",
        })
        row.update(status="queued", last_queued=day)

    order = {"dm": 0, "email": 1, "call": 2}
    queue.sort(key=lambda q: (order[q["channel"]], -q["score"]))
    for i, q in enumerate(queue, 1):
        q["rank"] = i
    out = os.path.join(args.out, day)
    store.save(os.path.join(out, "queue.csv"), queue, store.QUEUE_COLS)
    store.save(args.master, sorted(master.values(), key=lambda r: -int(r["score"] or 0)))
    write_report(os.path.join(out, "report.md"), day, master, queue)
    print(f"{len(queue)} queued for {day} -> {out}/queue.csv")


def write_report(path, day, master, queue):
    rows = list(master.values())
    count = lambda key, val: sum(1 for r in rows if r[key] == val)
    by_ch = {c: [q for q in queue if q["channel"] == c] for c in ("dm", "email", "call")}
    lines = [f"# Prospection SOGIXEL — {day}", "",
             f"**À faire aujourd'hui :** {len(by_ch['dm'])} DM · {len(by_ch['email'])} emails · {len(by_ch['call'])} appels", "",
             f"**Base :** {len(rows)} cliniques · {count('tier', 'Hot')} Hot · {count('tier', 'Warm')} Warm · {count('tier', 'Cold')} Cold",
             f"**Pipeline :** {count('status', 'sent')} contactées · {count('status', 'replied')} réponses · "
             f"{count('status', 'call_booked')} appels pris · {count('status', 'client')} clients", ""]
    for c, title in (("dm", "DM Instagram"), ("email", "Emails"), ("call", "Appels")):
        if by_ch[c]:
            lines += [f"## {title}", ""] + [f"{q['rank']}. **{q['name']}** ({q['city']}, {q['tier']} {q['score']}) — {q['reasons']}"
                                             for q in by_ch[c]] + [""]
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def cmd_sync(cfg, args):
    master = store.load(args.master)
    changed = 0
    for path in args.files:
        for pid, q in store.load(path).items():
            new = store.SHEET_STATUS.get(q.get("status", "").strip().lower())
            row = master.get(pid)
            # never reopen a closed row, and "stop" always wins
            if row and new and row["status"] != new and (row["status"] not in store.CLOSED or new == "do_not_contact"
                                                         or store.PROGRESS.index(new) > store.PROGRESS.index(row["status"])):
                row["status"] = new
                changed += 1
    store.save(args.master, sorted(master.values(), key=lambda r: -int(r["score"] or 0)))
    print(f"{changed} statuses updated")


def cmd_stats(cfg, args):
    rows = list(store.load(args.master).values())
    print(f"{len(rows)} prospects")
    for key in ("tier", "vertical", "city", "status", "angle"):
        vals = {}
        for r in rows:
            vals[r[key]] = vals.get(r[key], 0) + 1
        print(f"  {key:<9} " + "  ".join(f"{k}={v}" for k, v in sorted(vals.items(), key=lambda kv: -kv[1])))


def main(argv=None):
    ap = argparse.ArgumentParser(prog="sogixel")
    ap.add_argument("command", choices=["pull", "daily", "sync", "stats"])
    ap.add_argument("files", nargs="*", help="queue CSVs for `sync`")
    ap.add_argument("--config", default=os.path.join(ROOT, "config.toml"))
    ap.add_argument("--master", default=os.path.join(ROOT, "data", "prospects.csv"))
    ap.add_argument("--out", default=os.path.join(ROOT, "out"))
    ap.add_argument("--cities", nargs="*")
    ap.add_argument("--verticals", nargs="*", choices=["aesthetic", "hair", "dental"])
    ap.add_argument("--date")
    args = ap.parse_args(argv)
    cfg = load_cfg(args.config)
    {"pull": cmd_pull, "daily": cmd_daily, "sync": cmd_sync, "stats": cmd_stats}[args.command](cfg, args)


if __name__ == "__main__":
    main()
