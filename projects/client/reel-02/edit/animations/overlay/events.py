"""Cue sheet for the three Reel 02 Q&A reels -> events_<reel>.js.

    REEL=q1 studio/.venv/bin/python edit/animations/overlay/events.py     # q1 | q2 | q3

Cues point at words by clip + source start time (stable across re-cuts) and
are converted to output time through <reel>/timeline.json. Only the beats the
reel contains are cued.

Phrase words: (src, role, color, text?)  role = small | key | script | num;
color = None | "navy" | "yellow" | "red"; text overrides the transcript
spelling (or merges two words into one element). Each word enters on its own
timestamp. place = "below" (under the chin) | "above" (over the head).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

HERE = Path(__file__).resolve().parent
REEL = os.environ["REEL"]
TL = json.loads((HERE.parent.parent / REEL / "timeline.json").read_text())
WORDS = TL["words"]
RANGES = TL["ranges"]
BEATS = {r["beat"] for r in RANGES}
DUR = TL["duration"]


def w(src: float, clip: str) -> dict:
    hit = [x for x in WORDS if x["id"].startswith(clip) and abs(x["src"] - src) < 0.03]
    if not hit:
        raise KeyError(f"{clip} word at {src} is not in the cut")
    return min(hit, key=lambda x: abs(x["src"] - src))


def s(src: float, clip: str) -> float:
    return w(src, clip)["start"]


def e(src: float, clip: str) -> float:
    return w(src, clip)["end"]


def out(src: float, clip: str) -> float:
    """Output time of a source instant inside a kept range."""
    r = next(r for r in RANGES if r["source"] == clip and r["src_start"] - 0.02 <= src <= r["src_end"] + 0.02)
    return r["out_start"] + src - r["src_start"]


def beat_start(name: str) -> float:
    return next(r["out_start"] for r in RANGES if r["beat"] == name)


def beat_end(name: str) -> float:
    r = [r for r in RANGES if r["beat"] == name][-1]
    return r["out_start"] + r["duration"]


def range_at(src: float, clip: str) -> dict:
    return next(r for r in RANGES if r["source"] == clip and r["src_start"] - 0.02 <= src < r["src_end"])


def phrase(pid: str, clip: str, lines: list, end: float, y: int = 1250, x: int = 520, place: str = "below") -> dict:
    out_lines = []
    for line in lines:
        row = []
        for item in line:
            src, role, color, *text = item
            ww = w(src, clip)
            row.append({"t": text[0] if text else ww["word"], "at": round(ww["start"], 3), "role": role, "color": color})
        out_lines.append(row)
    start = min(x["at"] for line in out_lines for x in line)
    return {"id": pid, "start": round(start, 3), "end": round(end, 3), "x": x, "y": y, "lines": out_lines,
            "place": place, "parent": None}


C19, C25, C26, C22, C23, C28 = "C2419", "C2425", "C2426", "C2422", "C2423", "C2428"
PHRASES: list[dict] = []
EV: dict = {"duration": DUR, "reel": REEL, "cutaways": [], "gray": []}

# ---------------- q1: paid 2500 DH, scammed? -> the warranty card ----------------
if "Q1" in BEATS:
    PHRASES += [
        phrase("q1a", C19, [[(2.28, "small", None), (2.58, "small", None)]], end=s(4.15, C19)),
        phrase("q1b", C19, [[(4.15, "small", None), (5.05, "small", None)],
                            [(5.43, "key", "yellow", "غليظ"), (6.05, "key", "navy")]], end=s(6.86, C19)),
        phrase("q1c", C19, [[(6.86, "small", None), (7.30, "small", None)],
                            [(7.46, "key", "red", "تقولبت؟")]], end=beat_end("Q1") - 0.03),
    ]
    # price tag swings down on "2500", "DH" on "درهم"
    EV.update({"tag_in": s(2.94, C19), "tag_dh": s(3.89, C19), "tag_out": s(5.05, C19) - 0.1})
    EV["gray"].append([s(7.46, C19), beat_end("Q1") - 0.05])
if "A1" in BEATS:
    white = range_at(66.22, C19)               # white card close-up (l'indice)
    green_end = out(58.60, C19)                # end of the green-card close-up
    PHRASES += [
        phrase("a1a", C19, [[(50.88, "small", None), (51.23, "small", None)],
                            [(51.85, "key", "navy"), (52.61, "num", "red", "100%")]], end=s(53.77, C19)),
        phrase("a1b", C19, [[(53.77, "small", None)], [(54.55, "key", "yellow", "أهم حاجة")]], end=s(55.94, C19) - 0.1),
        phrase("a1c", C19, [[(55.94, "small", None, "la carte de")], [(56.40, "key", "navy", "garantie")]],
               end=s(57.98, C19), y=330, place="above"),
        phrase("a1d", C19, [[(57.98, "small", None), (58.14, "key", "navy")]], end=green_end, y=330, place="above"),
        phrase("a1e", C19, [[(64.48, "small", None), (65.47, "key", "yellow")]], end=white["out_start"] - 0.03),
        phrase("a1f", C19, [[(67.73, "small", None), (67.95, "key", "navy", "أول حاجة")]], end=s(68.75, C19)),
        phrase("a1g", C19, [[(68.75, "key", "yellow", "وثاني حاجة")]], end=s(70.15, C19)),
        phrase("a1h", C19, [[(70.15, "small", None), (70.53, "small", None), (70.77, "small", None)],
                            [(71.41, "key", "navy")]], end=s(72.13, C19)),
        phrase("a1i", C19, [[(72.13, "small", None), (72.73, "small", None), (73.57, "small", None)],
                            [(73.69, "key", "yellow", "l'expertise")]], end=s(75.81, C19)),
        phrase("a1j", C19, [[(75.81, "small", None)], [(76.80, "key", "navy", "le choix")]], end=s(77.98, C19)),
        phrase("a1k", C19, [[(77.98, "small", None), (78.52, "small", None)], [(78.70, "key", None, "les verres")]],
               end=beat_end("A1") - 0.03),
    ]
    EV.update({
        # "قالك l'opticien ... درت لك واحد l'indice" speech bubble
        "said_in": s(61.12, C19), "said_type": s(63.32, C19), "said_out": s(64.48, C19) - 0.08,
        # white card close-up -> pointer "l'indice ✓"
        "callout_in": white["out_start"] + 0.12, "callout_out": white["out_start"] + white["duration"] - 0.04,
    })
    EV["cutaways"] += [out(55.70, C19), white["out_start"]]

# ---------------- q2: told to take a 1.74 -> the index table ----------------
if "Q2" in BEATS:
    PHRASES += [
        phrase("q2a", C25, [[(1.76, "small", None), (2.02, "small", None), (2.54, "small", None)],
                            [(3.39, "num", "yellow", "1.74")]], end=s(4.85, C25)),
        phrase("q2b", C25, [[(4.85, "key", "navy"), (5.09, "key", "navy", "بصح؟")]], end=s(5.88, C25)),
        phrase("q2c", C25, [[(5.88, "small", None), (6.08, "small", None), (6.34, "small", None)],
                            [(6.52, "key", "red"), (6.92, "key", "red", "كثر؟")]], end=beat_end("Q2") - 0.03),
    ]
    EV["gray"].append([s(6.52, C25), beat_end("Q2") - 0.05])
if "A2" in BEATS:
    table_in = s(7.53, C26) + 0.3              # "هنا غايبان ليكم": drops in as the camera tilt settles
    lens_in = s(35.99, C26) - 0.12             # "سميتو Master Luxe"
    PHRASES += [
        phrase("a2a", C26, [[(2.46, "script", "yellow", "ça dépend")], [(2.92, "key", "navy"), (3.26, "key", None)]],
               end=table_in - 0.05),
        phrase("a2b", C26, [[(33.59, "small", None), (34.09, "key", "navy", "des verres")],
                            [(34.61, "small", None), (35.09, "small", None, "ف Gzenaya")]], end=lens_in - 0.05),
    ]
    EV.update({
        "table_in": table_in, "table_out": s(33.33, C26) - 0.1,
        "hdr": [s(13.80, C26), s(15.20, C26)],
        "rows": [
            {"c": s(17.67, C26), "i": s(20.98, C26)},
            {"c": s(22.82, C26), "i": s(24.58, C26)},
            {"c": s(24.68, C26), "i": s(27.22, C26)},
            {"c": s(28.29, C26), "i": s(30.47, C26), "m": s(32.03, C26)},
        ],
        # "يعني كيفما كيقولو الناس البلاستيك" is cut from the reel (client, v4): no "plastique" pill
        "lens_in": lens_in, "lens_name": s(36.75, C26), "lens_org": s(39.48, C26),
        "lens_thin": s(43.28, C26), "lens_normal": s(44.78, C26), "lens_out": beat_end("A2") - 0.05,
    })

# ---------------- q3: -10, thick edges -> two frames, 48 -> 46 ----------------
if "Q3" in BEATS:
    PHRASES += [
        phrase("q3a", C22, [[(1.30, "small", None), (1.74, "small", None)], [(2.18, "num", "yellow", "-10")]],
               end=s(3.21, C22)),
        phrase("q3b", C22, [[(3.21, "small", None), (3.87, "small", None), (4.25, "small", None)],
                            [(4.65, "key", "yellow"), (4.93, "small", None, "من الجناب")]], end=s(5.78, C22)),
        phrase("q3c", C22, [[(5.78, "small", None), (6.08, "small", None), (6.36, "small", None)],
                            [(6.54, "key", "navy", "حل؟")]], end=beat_end("Q3") - 0.03),
    ]
if "A3" in BEATS:
    frame2 = range_at(10.12, C23)              # "وكاين هادي" (frame 2 close-up)
    PHRASES += [
        phrase("a3a", C23, [[(2.12, "script", "yellow", "Alors")], [(2.72, "key", "navy", "Gzenaya Optique")]],
               end=s(3.72, C23)),
        phrase("a3b", C23, [[(3.72, "script", "yellow", "bien sûr")],
                            [(4.12, "small", None), (4.37, "small", None), (4.55, "key", "yellow")]], end=s(5.73, C23)),
        phrase("a3c", C23, [[(5.73, "small", None), (6.19, "small", None)], [(7.23, "key", "navy", "deux montures")]],
               end=s(8.37, C23)),
        phrase("a3d", C23, [[(8.37, "small", None, "كاين هادي")], [(8.63, "num", "navy", "1")]], end=s(10.12, C23),
               y=200, place="above"),
        phrase("a3e", C23, [[(10.12, "small", None, "وكاين هادي")], [(10.50, "num", "yellow", "2")]],
               end=frame2["out_start"] + frame2["duration"] - 0.03, y=200, place="above"),
        phrase("a3f", C23, [[(21.91, "small", None), (22.43, "small", None)], [(23.10, "num", "navy", "1.74")]],
               end=s(24.34, C23)),
        phrase("a3g", C23, [[(24.34, "script", "yellow", "bien sûr")], [(24.82, "key", "red"), (25.26, "key", "red")]],
               end=beat_end("A3") - 0.03),
    ]
    EV.update({"arm_in": s(11.64, C23), "arm_digits": s(14.14, C23), "arm_d": s(16.69, C23), "arm_48": s(18.21, C23),
               "arm_46": s(20.37, C23), "arm_out": s(21.43, C23) - 0.15})
    EV["cutaways"] += [out(8.80, C23), out(10.10, C23)]
    EV["gray"].append([s(24.82, C23), beat_end("A3") - 0.05])
if "TEASE" in BEATS:
    PHRASES += [phrase("t3", C23, [[(32.37, "small", None, "le client"), (32.83, "small", None, "جا عندنا")]],
                       end=s(33.77, C23))]
    EV.update({"next_in": beat_start("TEASE") + 0.05, "next_case": s(30.05, C23), "next_old": s(34.26, C23),
               "next_new": s(35.48, C23), "next_out": beat_start("CTA") - 0.05})

# ---------------- CTA (same on every reel) ----------------
# C2428 is a tight shot: the lines go over his head, the save button under his chin
PHRASES += [
    phrase("c1", C28, [[(2.69, "small", None), (2.83, "key", "navy", "la vidéo")]], end=s(3.55, C28),
           y=170, place="above"),
    phrase("c2", C28, [[(3.55, "small", None), (4.03, "small", None), (4.11, "small", None), (4.27, "small", None),
                        (4.59, "small", None)], [(4.80, "key", "yellow", "نضاضر")]], end=DUR, y=170, place="above"),
]
EV.update({"save_in": s(2.16, C28) - 0.08, "save_fill": e(2.16, C28) - 0.1})

PHRASES.sort(key=lambda p: p["start"])
# one phrase at a time: each ends just before the next begins
for a, b in zip(PHRASES, PHRASES[1:]):
    a["end"] = round(min(a["end"], b["start"] - 0.05), 3)
EV["phrases"] = PHRASES

# question card, corner chips (no numbering: each reel stands alone), "جواب" wall on the answer
q = next(b for b in ("Q1", "Q2", "Q3") if b in BEATS)
a = {"Q1": "A1", "Q2": "A2", "Q3": "A3"}[q]
after = "TEASE" if "TEASE" in BEATS else "CTA"
EV["quiz"] = [{"t": round(beat_start(q), 3)}]
EV["chips"] = [{"kind": "q", "start": round(beat_start(q) + 1.15, 3), "end": round(beat_start(a), 3)},
               {"kind": "a", "start": round(beat_start(a) + 0.05, 3), "end": round(beat_start(after) - 0.05, 3)}]
EV["walls"] = [round(beat_start(a), 3)]

(HERE / f"events_{REEL}.js").write_text("window.EV = " + json.dumps(EV, ensure_ascii=False, indent=1) + ";\n",
                                         encoding="utf-8")
print(REEL, json.dumps({k: round(v, 2) for k, v in EV.items() if isinstance(v, (int, float))}, ensure_ascii=False))
print("  phrases:", [(p["id"], p["start"], p["end"]) for p in PHRASES])
