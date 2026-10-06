"""Cut list for Reel 02 (Q&A) -> edl.json + timeline.json.

Order (client-approved): Q1 > A1 > Q3 > A3 > Q2 > A2 > teaser > CTA.

KEEP lists the spoken passages (source seconds, first word start -> last word
end). Inside each passage, pauses are found on the lav energy, not on word
gaps: MoulSot/MMS squash some numbers ("1.60", "1.74") to near-zero-length
words, so word gaps would cut into speech. Every quiet run longer than
MIN_PAUSE is cut down to POST after the voice stops + PRE before it restarts.
Passage edges are refined on the same energy and clamped away from words that
are not kept (crew talk, dropped fillers). Pauses inside HOLD (he shows an
object to camera) are kept.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import numpy as np

FPS = 50
EDIT = Path(__file__).resolve().parent
SRC = EDIT.parent / "source"
MIN_PAUSE = 0.24    # quiet runs longer than this are cut
PRE, POST = 0.05, 0.09
ENERGY_DB = -31.0   # lav level that still counts as voice
CLIPS = ("C2419", "C2425", "C2426", "C2422", "C2423", "C2428")

# (beat, clip, first word start, last word end) in source seconds
KEEP = [
    ("Q1",    "C2419",  2.28,  7.92),   # خويا خلصت 2500 درهم ... واش تقولبت
    ("A1",    "C2419", 50.88, 79.38),   # ماشي ضروري ... les verres ديالك ("وهو" and "هادشي اللي كاين" dropped)
    ("Q3",    "C2425",  1.76,  7.12),   # قالو ليا خاصك un soixante-quatorze ...
    ("A3",    "C2426",  2.46,  3.58),   # ça dépend العبار ديالك
    ("A3",    "C2426",  7.53,  8.46),   # هنا غايبان ليكم  (0.25-steps aside and "des indices ولا des corrections" dropped)
    ("A3",    "C2426", 13.42, 45.10),   # وكل correction ... على 1.74 normal
    ("Q2",    "C2422",  1.30,  6.70),   # أنا عندي moins dix ... واش كاين شي حل
    ("A2",    "C2423",  2.12, 25.60),   # Alors عندك Gzenaya Optique ... غيطلع غليظ
    ("TEASE", "C2423", 27.44, 35.90),   # وف la vidéo الجاية ... والجديدة ("par rapport لهذا" dropped)
    ("CTA",   "C2428",  2.16,  6.00),   # سوفݣاردي هاد la vidéo ... إن شاء الله (+0.5s for the save button to land)
]

# visual moments inside pauses that must stay (he holds something up to camera)
HOLD = {"C2423": [(8.40, 10.10)]}   # "كاين هادي ... وكاين هادي": frame 1 raised, then frame 2


def lav_energy(clip: str) -> np.ndarray:
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(SRC / f"{clip}.MP4"), "-map", "0:a:0",
                          "-af", "pan=mono|c0=c0", "-ar", "16000", "-f", "s16le", "-"],
                         capture_output=True, check=True).stdout
    x = np.frombuffer(raw, np.int16).astype(np.float32) / 32768
    w = 160  # 10 ms
    x = x[: len(x) // w * w].reshape(-1, w)
    return 20 * np.log10(np.sqrt((x ** 2).mean(axis=1)) + 1e-9)


def load_words(clip: str) -> list[dict]:
    return sorted(json.loads((EDIT / "darija" / f"{clip}.words.json").read_text()), key=lambda w: w["start"])


def quiet_runs(e: np.ndarray, a: float, b: float) -> list[tuple[float, float]]:
    """Quiet stretches (energy below ENERGY_DB) longer than MIN_PAUSE inside [a, b]."""
    i0, i1 = int(a * 100), int(np.ceil(b * 100))
    q = e[i0:i1] < ENERGY_DB
    runs, start = [], None
    for k, v in enumerate(np.append(q, False)):
        if v and start is None:
            start = k
        elif not v and start is not None:
            if (k - start) / 100 >= MIN_PAUSE:
                runs.append(((i0 + start) / 100, (i0 + k) / 100))
            start = None
    return runs


def main() -> None:
    words = {c: load_words(c) for c in CLIPS}
    energy = {c: lav_energy(c) for c in CLIPS}

    ranges = []
    for beat, clip, a, b in KEEP:
        e = energy[clip]
        walls = [(w["start"], w["end"]) for w in words[clip] if w["end"] <= a - 0.005 or w["start"] >= b + 0.005]
        lo = max([en for st, en in walls if en <= a + 1e-6] + [0.0])
        hi = min([st for st, en in walls if st >= b - 1e-6] + [len(e) / 100])
        s = a - PRE
        while s - 0.01 > lo + 0.02 and s > a - PRE - 0.10 and e[int((s - 0.01) * 100)] > ENERGY_DB:
            s -= 0.01
        t = b + POST
        while t + 0.01 < hi - 0.02 and t < b + POST + 0.15 and e[int(t * 100)] > ENERGY_DB:
            t += 0.01
        s, t = max(s, lo + 0.02), min(t, hi - 0.02)
        # split at the pauses inside the passage
        pieces, cur = [], s
        for qa, qb in quiet_runs(e, s, t):
            if qa - cur < 0.05 or t - qb < 0.05:     # quiet edge of the passage: already trimmed
                continue
            if any(qa < hb and qb > ha for ha, hb in HOLD.get(clip, [])):
                continue
            pieces.append((cur, qa + POST))
            cur = qb - PRE
        pieces.append((cur, t))
        for ps, pt in pieces:
            ranges.append({"beat": beat, "source": clip, "f0": int(np.floor(ps * FPS)), "f1": int(np.ceil(pt * FPS))})

    merged = [ranges[0]]
    for r in ranges[1:]:
        m = merged[-1]
        if r["source"] == m["source"] and r["beat"] == m["beat"] and r["f0"] <= m["f1"] + 3:
            m["f1"] = max(m["f1"], r["f1"])
        else:
            merged.append(r)
    ranges = merged

    out_ranges, t_out = [], 0
    for r in ranges:
        n = r["f1"] - r["f0"]
        out_ranges.append({"beat": r["beat"], "source": r["source"], "src_start": r["f0"] / FPS,
                           "src_end": r["f1"] / FPS, "frames": n, "out_start": t_out / FPS, "duration": n / FPS})
        t_out += n

    def to_out(clip: str, beat: str, src: float) -> float:
        """Source time -> output time; times inside a cut snap to the next kept frame."""
        rs = [r for r in out_ranges if r["source"] == clip and r["beat"] == beat]
        for r in rs:
            if src < r["src_start"]:
                return r["out_start"]
            if src <= r["src_end"]:
                return r["out_start"] + src - r["src_start"]
        return rs[-1]["out_start"] + rs[-1]["duration"]

    out_words = []
    for beat, clip, a, b in KEEP:
        for w in words[clip]:
            if w["start"] >= a - 0.005 and w["end"] <= b + 0.005:
                out_words.append({"id": f"{clip}@{w['start']:.2f}", "word": w["word"], "beat": beat, "src": w["start"],
                                  "start": round(to_out(clip, beat, w["start"]), 3),
                                  "end": round(to_out(clip, beat, w["end"]), 3)})

    total = t_out / FPS
    (EDIT / "timeline.json").write_text(json.dumps(
        {"fps": FPS, "duration": total, "width": 1080, "height": 1920,
         "ranges": out_ranges, "words": out_words}, ensure_ascii=False, indent=1), encoding="utf-8")
    (EDIT / "edl.json").write_text(json.dumps({
        "version": 2,
        "sources": {c: str(SRC / f"{c}.MP4") for c in CLIPS},
        "ranges": [{"source": r["source"], "start": r["src_start"], "end": r["src_end"], "beat": r["beat"]}
                   for r in out_ranges],
        "total_duration_s": total,
    }, indent=1), encoding="utf-8")
    kept_src = sum(b - a for _, _, a, b in KEEP)
    print(f"{len(out_ranges)} ranges, {len(out_words)} words, {total:.2f}s (passages {kept_src:.1f}s)")
    for i, r in enumerate(out_ranges):
        ws = " ".join(w["word"] for w in out_words
                      if w["beat"] == r["beat"] and r["src_start"] - 0.03 <= w["src"] < r["src_end"])
        print(f"  {i:2d} {r['out_start']:6.2f}-{r['out_start'] + r['duration']:6.2f} {r['beat']:5} "
              f"{r['source']} {r['src_start']:6.2f}-{r['src_end']:6.2f}  {ws}")


if __name__ == "__main__":
    main()
