"""Graphic/caption cue times -> events.js.

Cues point at words by clip + source start time (stable across re-cuts) and
are converted to output time through timeline.json.
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


hook_words = [{"text": x["word"], "start": x["start"], "end": x["end"]} for x in WORDS if x["beat"] == "HOOK"]
hook_words[-1]["text"] += "؟"

EV = {
    "duration": TL["duration"],
    "hook_words": hook_words,
    # comment card
    "card_in": 0.0,
    "reply": s(6.27, "C2412"),                       # bien
    "card_out": beat_start("FIRST") - 0.22,
    # captions: [start, end, html]
    "captions": [
        [s(6.27, "C2412"), e(6.55, "C2412") + 0.04, "bien sûr"],
        [s(6.91, "C2412"), beat_start("FIRST") - 0.02, "<b>يقدرو يدوخوك</b>"],
        [s(8.70), e(9.56) + 0.3, "surtout <b>المرة اللولة</b>"],
        [s(10.50), e(10.94) + 0.1, "كانصح <b>الناس</b>"],
        [s(17.34), beat_start("WHY") - 0.02, "<b>مايسباريوش</b>"],
        [s(27.99) - 0.25, e(28.67) + 0.1, "تادابطا على <b>les progressifs</b>"],
        [s(41.52), min(e(41.52) + 0.35, s(43.74) - 0.3), "<b>ماولفتيهمش</b>؟"],
        [s(46.50), e(46.80) + 0.3, "<b>ترجع عندنا</b>"],
        [s(53.35), e(53.35) + 0.3, "<b>فالكومونتير</b>"],
        [s(54.91) - 0.1, TL["duration"], "<b>la vidéo الجاية</b>"],
    ],
    # +1 / +2
    "add_in": s(15.28) - 0.55,
    "plus1": s(15.28),
    "plus2": s(15.88),
    "add_out": s(17.34) - 0.1,
    # loin / pres, then "separately" = X
    "loin": s(20.61),
    "pres": s(21.51),
    "sep": s(22.11),
    "lp_out": s(22.63) + 0.25,
    # addition gauge
    "gauge_in": s(23.33) - 0.2,
    "gauge_rise": s(23.97),
    "plus3": s(25.83) - 0.15,
    "hard": s(27.19),
    "gauge_out": s(27.99) - 0.3,
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
    "back_in": s(46.80) + 0.3,
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
print(json.dumps({k: round(v, 2) for k, v in EV.items() if not isinstance(v, list)}, ensure_ascii=False))
