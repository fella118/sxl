"""Cue sheet -> events.js (v3: phrase typography + depth treatments).

Cues point at words by clip + source start time (stable across re-cuts) and
are converted to output time through timeline.json.

Phrase words: (src, role, color, text?)  role = small | key | script | num;
color = None | "cyan" | "yellow" | "red"; text overrides the transcript
spelling (e.g. "adition" -> "addition"). Each word enters on its own timestamp.
"""

from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
TL = json.loads((HERE.parent.parent / "timeline.json").read_text())
WORDS = TL["words"]


def w(src: float, clip: str = "C2416") -> dict:
    hit = [x for x in WORDS if x["id"].startswith(clip) and abs(x["src"] - src) < 0.03]
    if not hit:
        raise KeyError(f"{clip} word at {src} is not in the cut")
    return hit[0]


def s(src: float, clip: str = "C2416") -> float:
    return w(src, clip)["start"]


def e(src: float, clip: str = "C2416") -> float:
    return w(src, clip)["end"]


def beat_start(name: str) -> float:
    return next(r["out_start"] for r in TL["ranges"] if r["beat"] == name)


def phrase(pid: str, lines: list, end: float, y: int = 1250, clip: str = "C2416", x: int = 540) -> dict:
    out_lines = []
    for line in lines:
        out = []
        for item in line:
            src, role, color, *text = item
            ww = w(src, clip)
            out.append({"t": text[0] if text else ww["word"], "at": round(ww["start"], 3), "role": role,
                        "color": color})
        out_lines.append(out)
    start = min(x["at"] for line in out_lines for x in line)
    return {"id": pid, "start": round(start, 3), "end": round(end, 3), "x": x, "y": y, "lines": out_lines}


hook_words = [{"text": x["word"], "start": x["start"], "end": x["end"]} for x in WORDS if x["beat"] == "HOOK"]
hook_words[-1]["text"] += "؟"

PHRASES = [
    phrase("bien", [[(6.27, "script", "yellow", "bien sûr")],
                    [(6.91, "small", None), (7.25, "key", "cyan")]],
           end=beat_start("FIRST") - 0.04, clip="C2412", y=1240),
    phrase("first", [[(8.70, "script", "yellow")],
                     [(9.22, "small", None), (9.56, "key", None)]],
           end=e(9.56) + 0.32),
    phrase("advise", [[(10.32, "small", None), (10.50, "key", "cyan"), (10.94, "small", None)]],
           end=e(10.94) + 0.18),
    phrase("addition", [[(11.92, "small", None, "une fois"), (12.20, "small", None), (12.52, "small", None)],
                        [(12.92, "key", "yellow", "addition")]],
           end=beat_start("ADD12") - 0.04),
    phrase("still", [[(14.10, "small", None), (14.40, "small", None)],
                     [(15.06, "num", "cyan", "+1"), (15.48, "small", None), (15.66, "num", "cyan", "+2")]],
           end=s(16.54) - 0.06, y=520),
    phrase("pref", [[(16.54, "script", "yellow", "de préférence")],
                    [(17.34, "key", None)]],
           end=beat_start("WHY") - 0.04),
    phrase("chart_title", [[(22.89, "small", None), (23.33, "small", None), (23.97, "key", "cyan", "l'addition")]],
           end=s(27.19) - 0.08, y=150),
    phrase("adapt", [[(27.99, "small", None), (28.39, "small", None)],
                     [(28.55, "small", None), (28.67, "key", "cyan", "progressifs")]],
           end=s(29.25) - 0.1),
    phrase("notused", [[(40.78, "small", None)],
                       [(41.52, "key", "yellow", "ماولفتيهمش؟")]],
           end=s(43.74) - 0.3),
    phrase("back", [[(45.82, "script", "yellow", "de préférence")],
                    [(46.50, "key", "cyan", "ترجع عندنا")]],
           end=e(46.80) + 0.35),
    phrase("comment", [[(53.35, "key", "cyan")]], end=e(53.35) + 0.3),
    phrase("next", [[(54.91, "script", "yellow", "la vidéo")], [(55.27, "key", None)]],
           end=TL["duration"]),
]

# one phrase at a time: each ends just before the next begins
for a, b in zip(PHRASES, PHRASES[1:]):
    a["end"] = round(min(a["end"], b["start"] - 0.05), 3)

EV = {
    "duration": TL["duration"],
    "hook_words": hook_words,
    # comment card: types the comment, the reply badge lands, the card leaves on the cut
    "card_in": 0.0,
    "reply": e(4.70, "C2412") - 0.05,
    "card_out": beat_start("ANSWER") - 0.06,
    "phrases": PHRASES,
    # dizzy rings orbit his head on "يقدرو يدوخوك"
    "rings_in": s(6.91, "C2412") - 0.1,
    "rings_out": beat_start("FIRST") - 0.05,
    # loin / pres curved cards, then "separately" = X (+ grayscale)
    "loin": s(20.61),
    "pres": s(21.51),
    "sep": s(22.11),
    "lp_out": s(22.63) + 0.2,
    # chart reveal: difficulty grows with the addition
    "chart_in": s(22.63) + 0.24,          # after the loin/près cards leave
    "bar2": s(23.97),
    "plus3": s(25.83) - 0.15,
    "chart_out": s(27.19) - 0.08,
    # "صعاب" wall behind him + grayscale
    "wall_in": s(27.19) - 0.04,
    "wall_out": s(27.99) - 0.12,
    "gray": [[s(22.11), s(22.63) + 0.15], [s(27.19) - 0.04, s(27.99) - 0.1]],
    # floating glasses icons around "les progressifs"
    "float_in": s(28.55) - 0.1,
    "float_out": s(29.25) - 0.1,
    # criteria checklist
    "crit_in": s(29.89) - 0.2,
    "crit": [s(32.27), s(33.21), s(36.86), s(38.06)],
    "crit_q": s(39.18),
    "crit_out": beat_start("ADAPT") - 0.05,
    # 3 days
    "days_in": s(43.74) - 0.2,
    "days_hit": s(44.68),
    "days_out": s(45.98) + 0.2,
    # come back -> centrage -> professional
    "back_in": e(46.80) + 0.4,
    "back_check": s(48.01),
    "pro": s(49.59) - 0.15,
    "back_out": beat_start("CTA") - 0.05,
    # CTA
    "cta_in": s(51.25) - 0.1,
    "cta_type": s(52.55),
    "cta_send": s(53.35),
    "cta_next": s(54.11),
}

(HERE / "events.js").write_text("window.EV = " + json.dumps(EV, ensure_ascii=False, indent=1) + ";\n",
                                encoding="utf-8")
print(json.dumps({k: round(v, 2) for k, v in EV.items() if isinstance(v, (int, float))}, ensure_ascii=False))
print("phrases:", [(p["id"], p["start"], p["end"]) for p in PHRASES])
