"""Cue sheet for the vision-test reel -> events.js.

Cues point at words by clip + source start time and are converted to output
time through ../../timeline.json. The silent TEST pad is timed from its range.

Phrase words: (src, role, color, text?)  role = small | key | script | num;
color = None | "navy" | "yellow" | "red".
"""

from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
TL = json.loads((HERE.parent.parent / "timeline.json").read_text())
WORDS, RANGES, DUR = TL["words"], TL["ranges"], TL["duration"]
C30, C37, C38 = "C2430", "C2437", "C2438"


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


def phrase(pid: str, clip: str, lines: list, end: float, y: int = 1250, x: int = 520, place: str = "below") -> dict:
    out_lines = []
    for line in lines:
        row = []
        for src, role, color, *text in line:
            ww = w(src, clip)
            row.append({"t": text[0] if text else ww["word"], "at": round(ww["start"], 3), "role": role, "color": color})
        out_lines.append(row)
    start = min(x["at"] for line in out_lines for x in line)
    return {"id": pid, "start": round(start, 3), "end": round(end, 3), "x": x, "y": y, "lines": out_lines,
            "place": place, "parent": None}


HOOK, HOW, TEST, CTA = beat("HOOK"), beat("HOW"), beat("TEST"), beat("CTA")

PHRASES = [
    # "شوف!" is carried by the STOP sign on frame 1
    phrase("h2", C30, [[(2.20, "small", None, "فقل من")], [(2.69, "num", "yellow", "10"), (3.03, "key", "navy", "ثواني")]],
           end=s(3.71, C30)),
    phrase("h3", C30, [[(3.71, "small", None, "هاد le test"), (4.51, "small", None, "كافي باش تعرف")],
                       [(5.73, "small", None, "واش عندك"), (6.19, "key", "yellow", "نقص النظر؟")]], end=HOOK[1] - 0.04),
    # CTA: the comment box sits over his head, the question under his chin
    phrase("c1", C38, [[(2.61, "small", None, "شحال شفتي من")], [(3.55, "key", "navy", "اتجاه"), (4.08, "small", None, "ف كل عين؟")]],
           end=DUR - 0.6),
]
for a, b in zip(PHRASES, PHRASES[1:]):
    a["end"] = round(min(a["end"], b["start"] - 0.05), 3)

t0 = TEST[0]
EV = {
    "duration": DUR,
    "phrases": PHRASES,
    # hook: STOP sign + test card with a turning E (also the loop's last state)
    "hook_end": HOW[0],
    "gray": [[s(6.19, C30), HOOK[1] - 0.05]],
    # how-to steps (one at a time in the panel over his head)
    "steps": [
        {"k": "below", "t": HOW[0] + 0.05},           # غاتبان ليكم واحد التصويرة لتحت
        {"k": "dist", "t": s(4.12, C37)},             # غاتبعدوها واحد تلاتة ميترو
        {"k": "letter", "t": s(6.95, C37)},           # وغيبانولك les E
        {"k": "dirs", "t": s(9.77, C37)},             # خاصك تقولنا الاتجاه ديالهم
        {"k": "eye", "t": s(13.63, C37)},             # وغنبداو œil par œil غانغمضو عين
        {"k": "four", "t": s(16.34, C37)},            # وغتحاول تديتيكطي ربعة ديال les E
    ],
    "dist_num": s(5.59, C37),                         # "تلاتة ميترو"
    "dirs": [s(11.69, C37), s(12.09, C37), s(12.59, C37), s(13.03, C37)],   # ليمن ليسر لفوق لتحت
    "eye_close": s(15.40, C37),
    "four_pop": s(18.08, C37),
    "steps_out": HOW[1] - 0.05,
    # the test: full-screen chart, right eye then left eye
    "test_in": t0, "right_in": t0 + 0.45, "switch": t0 + 4.05, "left_in": t0 + 4.65, "test_out": TEST[1] - 0.3,
    # answers (for the pinned comment); directions the open side of the E faces
    "right_set": ["right", "down", "left", "up"],
    "left_set": ["up", "left", "right", "down"],
    # CTA
    "cta_in": s(0.92, C38) - 0.05,
    "cta_type": s(2.03, C38),
    "cta_send": s(4.44, C38) + 0.15,
    "loop_in": DUR - 0.55,
}
(HERE / "events.js").write_text("window.EV = " + json.dumps(EV, ensure_ascii=False, indent=1) + ";\n", encoding="utf-8")
print(json.dumps({k: round(v, 2) for k, v in EV.items() if isinstance(v, (int, float))}, ensure_ascii=False))
print("steps:", [(x["k"], round(x["t"], 2)) for x in EV["steps"]])
print("phrases:", [(p["id"], p["start"], p["end"]) for p in PHRASES])
