"""Cut list for the comment hook reel -> edl.json + timeline.json.

Every range is frame-aligned at 50 fps. timeline.json maps each kept word to
its output time so captions, typing and graphics land on the spoken syllable.
Zoom keys are (time within range, scale), scale relative to the full 9:16 frame.
"""

from __future__ import annotations

import json
from pathlib import Path

FPS = 50
EDIT = Path(__file__).resolve().parent
SRC = EDIT.parent / "source"

# beat, clip, start, end, zoom keys (t_in_range, scale) -- times in source seconds
RANGES = [
    ("HOOK",    "C2412",  2.74,  5.36, [(0, 1.00), ("end", 1.10)]),
    ("ANSWER",  "C2412",  6.18,  7.88, [(0, 1.24), ("end", 1.27)]),
    ("FIRST",   "C2416",  8.62, 13.42, [(0, 1.04), ("end", 1.10)]),
    ("ADD12",   "C2416", 14.06, 18.12, [(0, 1.18), ("end", 1.22)]),
    # loin/pres -> zoom in on +3 -> zoom out for the criteria checklist
    ("WHY",     "C2416", 19.56, 35.80, [(0, 1.04), (5.6, 1.06), (6.0, 1.22), (9.4, 1.24), (9.9, 1.04), ("end", 1.07)]),
    ("CORRECT", "C2416", 36.66, 40.12, [(0, 1.16), ("end", 1.19)]),
    ("ADAPT",   "C2416", 40.76, 44.12, [(0, 1.05), ("end", 1.08)]),
    ("RETURN",  "C2416", 44.60, 50.38, [(0, 1.12), (4.3, 1.14), (4.7, 1.24), ("end", 1.25)]),
    ("CTA",     "C2416", 50.60, 56.30, [(0, 1.02), ("end", 1.20)]),
]


def frames(t: float) -> int:
    return round(t * FPS)


def main() -> None:
    words = {c: json.loads((EDIT / "darija" / f"{c}.words.json").read_text()) for c in ("C2412", "C2416")}
    out_ranges, out_words, t_out = [], [], 0
    for beat, clip, s, e, zoom in RANGES:
        f0, f1 = frames(s), frames(e)
        n = f1 - f0
        dur = n / FPS
        keys = [(dur if k == "end" else k, z) for k, z in zoom]
        out_ranges.append({"beat": beat, "source": clip, "src_start": f0 / FPS, "src_end": f1 / FPS,
                           "frames": n, "out_start": t_out / FPS, "duration": dur, "zoom": keys})
        for i, w in enumerate(words[clip]):
            if w["start"] >= f0 / FPS - 0.01 and w["end"] <= f1 / FPS + 0.01:
                out_words.append({"id": f"{clip}:{i}", "word": w["word"], "beat": beat,
                                  "start": round(t_out / FPS + w["start"] - f0 / FPS, 3),
                                  "end": round(t_out / FPS + w["end"] - f0 / FPS, 3)})
        t_out += n

    total = t_out / FPS
    (EDIT / "timeline.json").write_text(json.dumps(
        {"fps": FPS, "duration": total, "width": 1080, "height": 1920,
         "ranges": out_ranges, "words": out_words}, ensure_ascii=False, indent=1), encoding="utf-8")
    (EDIT / "edl.json").write_text(json.dumps({
        "version": 1,
        "sources": {c: str(SRC / f"{c}.MP4") for c in ("C2412", "C2416")},
        "ranges": [{"source": r["source"], "start": r["src_start"], "end": r["src_end"], "beat": r["beat"]}
                   for r in out_ranges],
        "total_duration_s": total,
    }, indent=1), encoding="utf-8")
    print(f"{len(out_ranges)} ranges, {len(out_words)} words, {total:.2f}s")
    for r in out_ranges:
        print(f"  {r['beat']:8} {r['source']} {r['src_start']:6.2f}-{r['src_end']:6.2f} -> "
              f"{r['out_start']:6.2f}-{r['out_start'] + r['duration']:6.2f}")


if __name__ == "__main__":
    main()
