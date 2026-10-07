"""Cue sheet for the presbyopia reel -> events.js.

Karaoke captions: each line lights its words one by one on their timestamps.
Words: (src, text?, key?) -> key words light up yellow instead of navy.
"""

from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
TL = json.loads((HERE.parent.parent / "timeline.json").read_text())
WORDS, RANGES, DUR = TL["words"], TL["ranges"], TL["duration"]
C49, C52 = "C2449", "C2452"


def w(src: float, clip: str) -> dict:
    hit = [x for x in WORDS if x["id"].startswith(clip) and abs(x["src"] - src) < 0.03]
    if not hit:
        raise KeyError(f"{clip} word at {src} is not in the cut")
    return min(hit, key=lambda x: abs(x["src"] - src))


def s(src: float, clip: str) -> float:
    return w(src, clip)["start"]


def beat(name: str) -> tuple[float, float]:
    rs = [r for r in RANGES if r["beat"] == name]
    return rs[0]["out_start"], rs[-1]["out_start"] + rs[-1]["duration"]


def line(clip: str, items: list, key: bool = False) -> dict:
    ws = []
    for it in items:
        src, *rest = it if isinstance(it, tuple) else (it,)
        ww = w(src, clip)
        ws.append({"t": rest[0] if rest and rest[0] else ww["word"].rstrip("،.").rstrip(","), "at": round(ww["start"], 3)})
    return {"start": ws[0]["at"], "words": ws, "key": key}


HOOK, ADVICE, SOL = beat("HOOK"), beat("ADVICE"), beat("SOL")
LINES = [
    line(C49, [27.27, 27.49, 27.99, 28.19]),                                   # يلا وصلتي لهاد المرحلة
    line(C49, [28.75, (29.07, "تباعد"), 29.38]),                               # أنك تباعد التيليفون
    line(C49, [30.04, 30.22, 30.50]),                                          # باش تشوف مزيان
    line(C49, [30.94, 31.14, 31.50]),                                          # هادي علامة كاتدل
    line(C49, [31.94, 32.14, 32.52]),                                          # على أنو عندك
    line(C49, [32.78, 33.12], key=True),                                       # مشكل فالقرب
    line(C52, [14.16, 14.58, 14.74, 15.04]),                                   # والنصيحة اللي نقدر نعطيك
    line(C52, [15.50, 15.80, 16.16, 16.89]),                                   # هو تمشي لأقرب وقت
    line(C52, [17.20, 17.71], key=True),                                       # لأقرب spécialiste
    line(C52, [18.49, 18.77, 18.95]),                                          # دوز على عينيك
    line(C52, [19.69, 20.37]),                                                 # وماتنساش تبارطاجي
    line(C52, [20.99, (21.19, "la vidéo"), 21.63]),                            # هاد la vidéo هادي
    line(C52, [21.93, 22.07, 22.31]),                                          # مع الناس اللي
    line(C52, [(22.47, "كتباعد"), 22.84, 23.52, 23.72]),                       # كتباعد التيليفون باش تشوف
]
for a, b in zip(LINES, LINES[1:]):
    a["end"] = round(min(b["start"], a["words"][-1]["at"] + 1.4) - 0.04, 3)
LINES[-1]["end"] = round(DUR - 0.02, 3)
# "la" + "vidéo" were merged: drop the duplicate "vidéo" timestamp entry if the transcript has both
hook_ranges = [r for r in RANGES if r["beat"] == "HOOK"]

EV = {
    "duration": DUR,
    "lines": LINES,
    # silent hook: headline + distance ruler while the arm stretches
    "hook_in": 0.25,
    "hook_out": hook_ranges[2]["out_start"] + 0.5,            # headline under his chin while the shot is close
    "ruler_in": hook_ranges[2]["out_start"] + 0.6,           # the camera has pulled back: ruler over his head
    "ruler_full": hook_ranges[3]["out_start"] + 0.4,         # arm fully stretched (slow motion)
    "ruler_out": HOOK[1] - 0.15,
    # advice: near blurry / far sharp card
    "near_in": s(30.94, C49) - 0.1,                          # هادي علامة
    "near_hit": s(32.78, C49),                               # مشكل فالقرب
    "near_out": ADVICE[1] - 0.1,
    # solution: three steps
    "tip_in": s(14.16, C52) - 0.05,                          # والنصيحة
    "tip_steps": [s(16.16, C52), s(17.20, C52), s(18.49, C52)],   # لأقرب وقت / لأقرب spécialiste / دوز على عينيك
    "tip_out": s(19.69, C52) - 0.1,
    # CTA: share + save
    "cta_in": s(19.69, C52) - 0.05,                          # وماتنساش
    "share_tap": s(20.37, C52) + 0.1,                        # تبارطاجي
    "save_tap": s(21.63, C52),                               # هادي (after la vidéo)
    "gray": [[s(32.78, C49), ADVICE[1] - 0.05]],
}
(HERE / "events.js").write_text("window.EV = " + json.dumps(EV, ensure_ascii=False, indent=1) + ";\n", encoding="utf-8")
print(json.dumps({k: round(v, 2) for k, v in EV.items() if isinstance(v, (int, float))}, ensure_ascii=False))
print("lines:", [(round(l["start"], 2), l["end"], " ".join(x["t"] for x in l["words"])) for l in LINES])
