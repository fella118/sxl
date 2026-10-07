"""Cut lists for Reel 02, split into three standalone Q&A reels -> <reel>/edl.json + timeline.json.

  q1: Q1 (paid 2500 DH, scammed?)  > A1 (warranty card)            > CTA
  q2: Q2 (told to take a 1.74)     > A2 (index table, MASTERY Luxe) > CTA
  q3: Q3 (-10, thick edges)        > A3 (two frames, 48 -> 46) > teaser > CTA

KEEP lists the spoken passages (source seconds, first word start -> last word
end). Inside each passage everything that is not speech is cut down to POST
after the voice stops + PRE before it restarts: dead air, breaths, lip noise.
"Speech" per 10 ms frame = the lav is above -31 dB and either Silero VAD says
speech or the sound is voiced (edit/vad_probs.py, edit/fillers.py): breaths are
loud but unvoiced and Silero scores them as non-speech. Word
gaps are not used: MMS squashes some numbers (1.60, 1.74) to near-zero words.
The filler scan (edit/fillers.py) found no free-standing "euh/aah": the long
"words" were pauses inside the aligned span, which this cut removes.

    studio/.venv/bin/python edit/cut.py            # all three reels
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

FPS = 50
EDIT = Path(__file__).resolve().parent
SRC = EDIT.parent / "source"
AUD = EDIT / "analysis_audio"
MIN_PAUSE = 0.12    # non-speech runs longer than this are cut
PRE, POST = 0.04, 0.06
ENERGY_DB = -31.0   # below this the lav is room tone / breath floor
MIN_RANGE = 0.40    # shorter ranges are joined to their closest neighbour (no 0.3 s framing flickers)
CLIPS = ("C2419", "C2425", "C2426", "C2422", "C2423", "C2428")

# (beat, clip, first word start, last word end) in source seconds
KEEP = [
    ("Q1",    "C2419",  2.28,  7.92),   # خويا خلصت 2500 درهم ... واش تقولبت
    ("A1",    "C2419", 50.88, 79.38),   # ماشي ضروري ... les verres ديالك ("وهو", "هادشي اللي كاين" dropped)
    ("Q2",    "C2425",  1.76,  7.12),   # قالو ليا خاصك un soixante-quatorze ...
    ("A2",    "C2426",  2.46,  3.58),   # ça dépend العبار ديالك
    ("A2",    "C2426",  7.53,  8.46),   # هنا غايبان ليكم  (0.25-steps aside, "des indices ولا des corrections" dropped)
    ("A2",    "C2426", 13.42, 45.10),   # وكل correction ... على 1.74 normal
    ("Q3",    "C2422",  1.30,  6.70),   # أنا عندي moins dix ... واش كاين شي حل
    ("A3",    "C2423",  2.12, 25.60),   # Alors عندك Gzenaya Optique ... غيطلع غليظ
    ("TEASE", "C2423", 27.44, 35.90),   # وف la vidéo الجاية ... والجديدة ("par rapport لهذا" dropped)
    ("CTA",   "C2428",  2.16,  6.00),   # سوفݣاردي هاد la vidéo ... إن شاء الله (+0.45 s for the save button)
]
REELS = {"q1": ["Q1", "A1", "CTA"], "q2": ["Q2", "A2", "CTA"], "q3": ["Q3", "A3", "TEASE", "CTA"]}
# visual moments inside pauses that stay (he holds something up to camera)
HOLD = {"C2423": [(9.00, 9.55)]}    # frame 1 raised, between "كاين هادي" and "وكاين هادي"


def speech_mask(clip: str) -> np.ndarray:
    d = np.load(AUD / f"{clip}.npz")
    e, v = d["energy"], d["voicing"]
    vad = np.load(AUD / f"{clip}_vad.npy")
    n = min(len(e), len(vad))
    e, v, vad = e[:n], v[:n], vad[:n]
    keep = (e > ENERGY_DB) & ((vad >= 0.5) | (v > 0.6))
    for a, b in HOLD.get(clip, []):
        keep[int(a * 100):int(b * 100)] = True
    return keep


def load_words(clip: str) -> list[dict]:
    return sorted(json.loads((EDIT / "darija" / f"{clip}.words.json").read_text()), key=lambda w: w["start"])


def nonspeech_runs(keep: np.ndarray, a: float, b: float) -> list[tuple[float, float]]:
    i0, i1 = int(a * 100), int(np.ceil(b * 100))
    q = ~keep[i0:i1]
    runs, start = [], None
    for k, val in enumerate(np.append(q, False)):
        if val and start is None:
            start = k
        elif not val and start is not None:
            if (k - start) / 100 >= MIN_PAUSE:
                runs.append(((i0 + start) / 100, (i0 + k) / 100))
            start = None
    return runs


def passage_ranges(beat: str, clip: str, a: float, b: float, words: list[dict], keep: np.ndarray) -> list[dict]:
    walls = [(w["start"], w["end"]) for w in words if w["end"] <= a - 0.005 or w["start"] >= b + 0.005]
    lo = max([en for st, en in walls if en <= a + 1e-6] + [0.0])
    hi = min([st for st, en in walls if st >= b - 1e-6] + [len(keep) / 100])
    s = a - PRE
    while s - 0.01 > lo + 0.02 and s > a - PRE - 0.10 and keep[int((s - 0.01) * 100)]:
        s -= 0.01
    t = b + POST
    while t + 0.01 < hi - 0.02 and t < b + POST + 0.20 and keep[int(t * 100)]:
        t += 0.01
    s, t = max(s, lo + 0.02), min(t, hi - 0.02)
    pieces, cur = [], s
    for qa, qb in nonspeech_runs(keep, s, t):
        if qa - cur < 0.03:                       # passage opens on non-speech: trim it
            cur = max(cur, qb - PRE)
            continue
        if t - qb < 0.03:                         # passage ends on non-speech: keep POST of it
            t = min(t, qa + POST) if beat != "CTA" else t
            continue
        pieces.append((cur, qa + POST))
        cur = qb - PRE
    pieces.append((cur, t))
    return [{"beat": beat, "source": clip, "f0": int(np.floor(ps * FPS)), "f1": int(np.ceil(pt * FPS))}
            for ps, pt in pieces if pt - ps > 0.04]


def build(reel: str, words: dict, keeps: dict) -> None:
    beats = REELS[reel]
    passages = [k for k in KEEP if k[0] in beats]
    passages.sort(key=lambda k: beats.index(k[0]))           # reel order, passages in source order per beat
    ranges = []
    for beat, clip, a, b in passages:
        ranges += passage_ranges(beat, clip, a, b, words[clip], keeps[clip])
    merged = [ranges[0]]
    for r in ranges[1:]:
        m = merged[-1]
        if r["source"] == m["source"] and r["beat"] == m["beat"] and r["f0"] <= m["f1"] + 2:
            m["f1"] = max(m["f1"], r["f1"])
        else:
            merged.append(r)
    # join ranges shorter than MIN_RANGE to the nearest same-source neighbour (the small gap comes back)
    while True:
        short = [i for i, r in enumerate(merged) if (r["f1"] - r["f0"]) / FPS < MIN_RANGE]
        done = True
        for i in short:
            nb = []
            for j in (i - 1, i + 1):
                if 0 <= j < len(merged) and merged[j]["source"] == merged[i]["source"] and merged[j]["beat"] == merged[i]["beat"]:
                    gap = merged[i]["f0"] - merged[j]["f1"] if j < i else merged[j]["f0"] - merged[i]["f1"]
                    if gap / FPS <= 0.35:
                        nb.append((gap, j))
            if nb:
                _, j = min(nb)
                a, b = sorted((i, j))
                merged[a] = {**merged[a], "f0": min(merged[a]["f0"], merged[b]["f0"]), "f1": max(merged[a]["f1"], merged[b]["f1"])}
                del merged[b]
                done = False
                break
        if done:
            break
    out_ranges, t_out = [], 0
    for r in merged:
        n = r["f1"] - r["f0"]
        out_ranges.append({"beat": r["beat"], "source": r["source"], "src_start": r["f0"] / FPS,
                           "src_end": r["f1"] / FPS, "frames": n, "out_start": t_out / FPS, "duration": n / FPS})
        t_out += n

    def to_out(clip: str, beat: str, src: float) -> float:
        rs = [r for r in out_ranges if r["source"] == clip and r["beat"] == beat]
        for r in rs:
            if src < r["src_start"]:
                return r["out_start"]
            if src <= r["src_end"]:
                return r["out_start"] + src - r["src_start"]
        return rs[-1]["out_start"] + rs[-1]["duration"]

    out_words = []
    for beat, clip, a, b in passages:
        for w in words[clip]:
            if w["start"] >= a - 0.005 and w["end"] <= b + 0.005:
                out_words.append({"id": f"{clip}@{w['start']:.2f}", "word": w["word"], "beat": beat, "src": w["start"],
                                  "start": round(to_out(clip, beat, w["start"]), 3),
                                  "end": round(to_out(clip, beat, w["end"]), 3)})
    total = t_out / FPS
    out = EDIT / reel
    out.mkdir(exist_ok=True)
    (out / "timeline.json").write_text(json.dumps(
        {"reel": reel, "fps": FPS, "duration": total, "width": 1080, "height": 1920,
         "ranges": out_ranges, "words": out_words}, ensure_ascii=False, indent=1), encoding="utf-8")
    (out / "edl.json").write_text(json.dumps({
        "version": 2,
        "sources": {c: str(SRC / f"{c}.MP4") for c in sorted({r["source"] for r in out_ranges})},
        "ranges": [{"source": r["source"], "start": r["src_start"], "end": r["src_end"], "beat": r["beat"]}
                   for r in out_ranges],
        "total_duration_s": total,
    }, indent=1), encoding="utf-8")
    spoken = sum(b - a for bt, _, a, b in passages)
    print(f"{reel}: {len(out_ranges)} ranges, {len(out_words)} words, {total:.2f}s (passages {spoken:.1f}s)")
    if "-v" in sys.argv:
        for i, r in enumerate(out_ranges):
            ws = " ".join(w["word"] for w in out_words
                          if w["beat"] == r["beat"] and r["src_start"] - 0.03 <= w["src"] < r["src_end"])
            print(f"  {i:2d} {r['out_start']:6.2f}-{r['out_start'] + r['duration']:6.2f} {r['beat']:5} "
                  f"{r['source']} {r['src_start']:6.2f}-{r['src_end']:6.2f}  {ws}")


def main() -> None:
    words = {c: load_words(c) for c in CLIPS}
    keeps = {c: speech_mask(c) for c in CLIPS}
    for reel in REELS:
        build(reel, words, keeps)


if __name__ == "__main__":
    main()
