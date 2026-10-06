"""Graphic/caption cue times from timeline.json word timings -> events.js."""

from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
TL = json.loads((HERE.parent.parent / "timeline.json").read_text())
WORDS = TL["words"]


def w(text: str, near: float) -> dict:
    """The kept word matching `text` closest to output time `near`."""
    cands = [x for x in WORDS if text in x["word"]]
    if not cands:
        raise KeyError(text)
    return min(cands, key=lambda x: abs(x["start"] - near))


def s(text: str, near: float) -> float:
    return w(text, near)["start"]


def e(text: str, near: float) -> float:
    return w(text, near)["end"]


hook_words = [{"text": x["word"], "start": x["start"], "end": x["end"]} for x in WORDS if x["beat"] == "HOOK"]
hook_words[-1]["text"] += "؟"

EV = {
    "duration": TL["duration"],
    "hook_words": hook_words,
    # comment card
    "card_in": 0.0,
    "reply": s("bien", 2.7),
    "card_out": TL["ranges"][2]["out_start"] - 0.22,
    # captions: [start, end, html]
    "captions": [
        [s("bien", 2.7), e("sûr", 3.0) + 0.04, 'bien sûr'],
        [s("يقدرو", 3.35), TL["ranges"][2]["out_start"] - 0.02, '<b>يقدرو يدوخوك</b>'],
        [s("surtout", 4.4), e("اللولة", 5.3) + 0.45, 'surtout <b>المرة اللولة</b>'],
        [s("مايسباريوش", 12.4), TL["ranges"][4]["out_start"] - 0.02, '<b>مايسباريوش</b>'],
        [s("تادابطا", 21.6) - 0.3, e("progressifs", 22.3) + 0.1, 'تادابطا على <b>les progressifs</b>'],
        [s("ماولفتيهمش", 33.8), e("ماولفتيهمش", 33.8) + 0.5, '<b>ماولفتيهمش</b>؟'],
        [s("ترجع", 38.1), e("عندنا", 38.4) + 0.3, '<b>ترجع عندنا</b>'],
        [s("فالكومونتير", 44.8), e("فالكومونتير", 44.8) + 0.35, '<b>فالكومونتير</b>'],
        [s("la", 46.33) - 0.1, TL["duration"], '<b>la vidéo الجاية</b>'],
    ],
    # +1 / +2
    "add_in": s("1", 10.3) - 0.55,
    "plus1": s("1", 10.3),
    "plus2": s("2", 10.9),
    "add_out": s("مايسباريوش", 12.4) - 0.1,
    # loin / pres, then "separately" = X
    "loin": s("vision", 14.2),
    "pres": s("vision", 15.1),
    "sep": s("بوحديتهم", 15.7),
    "lp_out": s("حيت", 16.25) + 0.25,
    # addition gauge
    "gauge_in": s("طلعات", 16.95) - 0.2,
    "gauge_rise": s("l'addition", 17.6),
    "plus3": s("3", 19.45) - 0.15,
    "hard": s("صعاب", 20.8),
    "gauge_out": s("تادابطا", 21.6) - 0.35,
    # criteria checklist
    "crit_in": s("critères", 23.5) - 0.2,
    "crit": [s("centrage", 25.9), s("hauteur", 26.8), s("mesures", 29.6), s("correction", 30.8)],
    "crit_q": s("صحيحة", 31.9),
    "crit_out": TL["ranges"][6]["out_start"] - 0.05,
    # 3 days
    "days_in": s("واحد", 35.86) - 0.25,
    "days_hit": s("تلتيام", 36.3),
    "days_out": s("préférence", 37.6) + 0.2,
    # come back -> centrage -> professional
    "back_in": s("ترجع", 38.1) + 0.6,
    "back_check": s("centrage", 39.65),
    "pro": s("professionnel", 41.2) - 0.15,
    "back_out": TL["ranges"][8]["out_start"] - 0.05,
    # CTA
    "cta_in": s("تساؤل", 42.6) - 0.1,
    "cta_type": s("تقدر", 44.0),
    "cta_send": s("فالكومونتير", 44.8),
    "cta_next": s("ونجاوبوك", 45.5),
}

(HERE / "events.js").write_text("window.EV = " + json.dumps(EV, ensure_ascii=False, indent=1) + ";\n",
                                encoding="utf-8")
print(json.dumps({k: v for k, v in EV.items() if not isinstance(v, list)}, ensure_ascii=False, indent=0))
