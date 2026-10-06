"""Cut list v2 for the comment hook reel -> edl.json + timeline.json.

v2 (client notes): breaths and pauses between phrases removed, the false start
before "ماولفتيهمش" cut, "داكشي مثلا" filler cut.

KEEP lists the spoken passages (source word times). Inside them, every gap
longer than BREATH_GAP between words is cut down to PRE + POST of air.
Island edges are refined on the lav energy so word onsets and tails survive,
and are clamped away from words/false starts that are not kept.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import numpy as np

FPS = 50
EDIT = Path(__file__).resolve().parent
SRC = EDIT.parent / "source"
BREATH_GAP = 0.14   # gaps longer than this between kept words are cut
PRE, POST = 0.05, 0.09
ENERGY_DB = -31.0   # lav level that still counts as voice when refining edges

# (beat, clip, first word start, last word end) in source seconds
KEEP = [
    ("HOOK",    "C2412",  2.86,  5.21),
    ("ANSWER",  "C2412",  6.27,  7.75),
    ("FIRST",   "C2416",  8.70, 13.32),
    ("ADD12",   "C2416", 14.10, 18.02),
    ("WHY",     "C2416", 19.65, 35.72),
    ("CORRECT", "C2416", 36.74, 40.04),
    ("ADAPT",   "C2416", 40.78, 40.90),   # "يلا"
    ("ADAPT",   "C2416", 41.52, 42.62),   # "ماولفتيهمش" (after the false start)
    ("RETURN",  "C2416", 43.74, 50.25),   # "واحد تلتيام ... le professionnel"
    ("CTA",     "C2416", 50.69, 55.88),
]
# never let an edge reach into these (false start, fillers)
BLOCKED = {"C2416": [(40.93, 41.50), (42.70, 43.66)]}
# words.json merges the false start into one long word: replace it
WORD_FIX = {"C2416": [((41.6, 42.7), [("يلا", 40.78, 40.90), ("ماولفتيهمش", 41.52, 42.62)])]}


def lav_energy(clip: str) -> np.ndarray:
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(SRC / f"{clip}.MP4"), "-map", "0:a:0",
                          "-af", "pan=mono|c0=c0", "-ar", "16000", "-f", "s16le", "-"],
                         capture_output=True, check=True).stdout
    x = np.frombuffer(raw, np.int16).astype(np.float32) / 32768
    w = 160  # 10 ms
    x = x[: len(x) // w * w].reshape(-1, w)
    return 20 * np.log10(np.sqrt((x ** 2).mean(axis=1)) + 1e-9)


def load_words(clip: str) -> list[dict]:
    words = json.loads((EDIT / "darija" / f"{clip}.words.json").read_text())
    for (a, b), repl in WORD_FIX.get(clip, []):
        words = [w for w in words if not (w["start"] >= a and w["end"] <= b)]
        words += [{"word": t, "start": s, "end": e} for t, s, e in repl]
    return sorted(words, key=lambda w: w["start"])


def main() -> None:
    clips = ("C2412", "C2416")
    words = {c: load_words(c) for c in clips}
    energy = {c: lav_energy(c) for c in clips}

    islands = []   # (beat, clip, start, end, [words])
    for beat, clip, a, b in KEEP:
        kept = [w for w in words[clip] if w["start"] >= a - 0.005 and w["end"] <= b + 0.005]
        group = [kept[0]]
        for w in kept[1:]:
            if w["start"] - group[-1]["end"] > BREATH_GAP:
                islands.append([beat, clip, group])
                group = []
            group.append(w)
        islands.append([beat, clip, group])

    ranges = []
    for beat, clip, group in islands:
        e = energy[clip]
        others = [(w["start"], w["end"]) for w in words[clip]
                  if not any(w is g for g in group) and not any(abs(w["start"] - g["start"]) < 1e-6 for g in group)]
        walls = others + BLOCKED.get(clip, [])
        lo = max([en for st, en in walls if en <= group[0]["start"] + 1e-6] + [0.0])
        hi = min([st for st, en in walls if st >= group[-1]["end"] - 1e-6] + [1e9])
        s = group[0]["start"] - PRE
        while s - 0.01 > lo + 0.02 and s > group[0]["start"] - PRE - 0.10 and e[int((s - 0.01) * 100)] > ENERGY_DB:
            s -= 0.01
        t = group[-1]["end"] + POST
        while t + 0.01 < hi - 0.02 and t < group[-1]["end"] + POST + 0.15 and e[int(t * 100)] > ENERGY_DB:
            t += 0.01
        s, t = max(s, lo + 0.02), min(t, hi - 0.02)
        ranges.append({"beat": beat, "source": clip, "f0": int(np.floor(s * FPS)), "f1": int(np.ceil(t * FPS)),
                       "words": group})

    # islands whose padded edges touch or overlap are one continuous range (no cut)
    merged = [ranges[0]]
    for r in ranges[1:]:
        m = merged[-1]
        if r["source"] == m["source"] and r["f0"] <= m["f1"] + 3:
            m["f1"] = max(m["f1"], r["f1"])
            m["words"] = m["words"] + r["words"]
        else:
            merged.append(r)
    ranges = merged

    out_ranges, out_words, t_out = [], [], 0
    for r in ranges:
        n = r["f1"] - r["f0"]
        s0 = r["f0"] / FPS
        out_ranges.append({"beat": r["beat"], "source": r["source"], "src_start": s0, "src_end": r["f1"] / FPS,
                           "frames": n, "out_start": t_out / FPS, "duration": n / FPS})
        for w in r["words"]:
            idx = next((i for i, x in enumerate(words[r["source"]]) if x is w), None)
            out_words.append({"id": f"{r['source']}@{w['start']:.2f}", "word": w["word"], "beat": r["beat"],
                              "src": w["start"],
                              "start": round(t_out / FPS + w["start"] - s0, 3),
                              "end": round(t_out / FPS + w["end"] - s0, 3)})
        t_out += n

    total = t_out / FPS
    (EDIT / "timeline.json").write_text(json.dumps(
        {"fps": FPS, "duration": total, "width": 1080, "height": 1920,
         "ranges": out_ranges, "words": out_words}, ensure_ascii=False, indent=1), encoding="utf-8")
    (EDIT / "edl.json").write_text(json.dumps({
        "version": 2,
        "sources": {c: str(SRC / f"{c}.MP4") for c in clips},
        "ranges": [{"source": r["source"], "start": r["src_start"], "end": r["src_end"], "beat": r["beat"]}
                   for r in out_ranges],
        "total_duration_s": total,
    }, indent=1), encoding="utf-8")
    print(f"{len(out_ranges)} ranges, {len(out_words)} words, {total:.2f}s")
    for r in out_ranges:
        ws = " ".join(w["word"] for w in out_words if r["out_start"] <= w["start"] < r["out_start"] + r["duration"])
        print(f"  {r['out_start']:6.2f}-{r['out_start'] + r['duration']:6.2f} {r['beat']:7} "
              f"{r['source']} {r['src_start']:6.2f}-{r['src_end']:6.2f}  {ws}")


if __name__ == "__main__":
    main()
