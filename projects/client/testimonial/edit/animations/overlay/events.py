"""Cue sheet for the SOGIXEL testimonial -> events.js.

Captions: karaoke lines (each word lights on its timestamp). Words come from the
cut's timeline, with spelling fixes (FIX, keyed on clip@source time), words
the transcript merged into a cut "euhhh" put back (ADD), and dropped tokens
(None). Lines are set by hand (PHRASES, checked word by word against the
transcript); same-script runs keep their reading order in mixed Darija/French
lines. QPHRASES are the host's off-camera question (styled apart).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
TL = json.loads((HERE.parent.parent / "timeline.json").read_text())
WORDS, RANGES, DUR = TL["words"], TL["ranges"], TL["duration"]

FIX = {
    "C2408@2.82": "monsieur", "C2408@3.74": "Dnanou Atae",
    "C2408@8.95": "l'avis", "C2408@9.11": None,
    "C2408@11.92": "SOGIXEL", "C2408@12.22": None,
    "C2408@13.32": "سي", "C2408@13.44": "Atae", "C2408@13.76": "نخلي",
    "C2410@23.72": "حتى", "C2410@28.07": "الماگازان", "C2410@58.61": "فالماگازة", "C2410@62.71": "سعد",
    "C2410@20.60": "le", "C2410@9.14": "مع",
    "IMG_6057@9.18": "نعاونوك",
    # the host's question (MMS forced alignment scores "asi atae" far above "abdellah")
    "C2411@3.86": None, "C2411@4.14": None, "C2411@5.86": "أسي", "C2411@6.08": "Atae", "C2411@6.25": None,
}
# (clip, source time of the spoken word, text): words whose transcript token started inside a cut drawl
ADD = [("C2410", 36.80, "عيط"), ("C2410", 49.98, "الأمر"), ("C2410", 54.25, "تفاهمنا"), ("C2410", 62.36, "سي"),
       ("C2411", 3.53, "وبالنسبة ل")]   # the question starts at 3.52 (lav energy); the transcript began at 3.86
# caption lines, by phrase (checked word by word against the transcript)
PHRASES = """
اليوم معانا | monsieur Dnanou Atae | fondateur ديال une chaîne | des magasins d'optique | و une marque e-commerce
غادي يعطينا l'avis ديالو | و l'expérience ديالو | كيف كانت معانا ف SOGIXEL | سي Atae نخلي ليك الكلمة
باختصار نعاود ليكم | l'histoire ديالي | مع les agences marketing | déjà كنت بديت | مع d'autres agences
ولكن المشكل | اللي كنت كنلقى هو | le retour sur investissement
حتى جا السي سعد | عيط ليا فالتيليفون | أنا déjà الماگازان | كنت بديت فيه | ça fait واحد العام | بحال هكا
كانت الأمور ناعسة | عيط ليا السي سعد | حتى هو الصراحة | نفس الدخلة اللي كيدخلوها | الناس ديال الماركوتينغ كاملين
وحتى هو فهمني فهاد الأمر | تفاهمنا على le retour
أهم حاجة عندي فالماگازة | وجاب الله التيسير | مع سي سعد
وبالنسبة ل la durée | شحال نتا معانا أسي Atae
دابا ça fait واحد العام | grosso modo كانريكومندي | أي واحد يخدم مع سي سعد | وغيكون satisfait | إن شاء الله
يلا كنتي حتى نتايا عييتي | من les promesses | sans résultat | ما عليك غير تكليكي | على le lien | اللي تحت la vidéo
ف 30 secondes | عمر الفورمولير | وغنشوفو واش نقدرو نعاونوك
"""
KEYS = ("investissement", "ناعسة", "satisfait", "résultat")
QPHRASES = {"وبالنسبة ل la durée", "شحال نتا معانا أسي Atae"}
AR = re.compile(r"[؀-ۿ]")


def out_time(clip: str, src: float) -> float:
    for r in RANGES:
        if "speed" not in r and r["source"] == clip and r["src_start"] - 0.01 <= src <= r["src_end"]:
            return r["out_start"] + src - r["src_start"]
    raise KeyError(f"{clip}@{src} is not in the cut")


def words() -> list[dict]:
    ws = []
    for w in WORDS:
        txt = FIX.get(w["id"], w["word"])
        if txt is None:
            continue
        ws.append({"t": txt.rstrip(".,"), "at": w["start"], "end": w["end"], "clip": w["id"].split("@")[0]})
    for clip, src, txt in ADD:
        t = out_time(clip, src)
        ws.append({"t": txt, "at": round(t, 3), "end": round(t + 0.25, 3), "clip": clip})
    ws.sort(key=lambda x: x["at"])
    return ws


def lines(ws: list[dict]) -> list[dict]:
    phrases = [" ".join(p.split()) for row in PHRASES.strip().splitlines() for p in row.split("|")]
    out, i = [], 0
    for ph in phrases:
        j = i
        while j < len(ws) and len(" ".join(x["t"] for x in ws[i:j])) < len(ph):
            j += 1
        got = " ".join(x["t"] for x in ws[i:j])
        if got != ph:
            raise SystemExit(f"phrase {ph!r} does not match the words {got!r}")
        cur = ws[i:j]
        out.append({"start": cur[0]["at"], "words": [{"t": x["t"], "at": round(x["at"], 3)} for x in cur], "q": ph in QPHRASES})
        i = j
    if i != len(ws):
        raise SystemExit(f"{len(ws) - i} words left over: {' '.join(x['t'] for x in ws[i:])}")
    for a, b in zip(out, out[1:]):
        a["end"] = round(min(b["start"], a["words"][-1]["at"] + 1.2) - 0.03, 3)
    out[-1]["end"] = round(DUR - 0.02, 3)
    for ln in out:
        ln["key"] = any(k in x["t"] for x in ln["words"] for k in KEYS)
    return out


def beat(name: str) -> tuple[float, float]:
    rs = [r for r in RANGES if r["beat"] == name]
    return rs[0]["out_start"], rs[-1]["out_start"] + rs[-1]["duration"]


WS = words()
LINES = lines(WS)
STORY, CTA = beat("STORY"), beat("CTA")
cta_w = {w["t"]: w["at"] for w in WS if w["clip"] == "IMG_6057"}
EV = {
    "duration": DUR,
    "lines": LINES,
    "tag_out": 3.4,                                  # "AVIS CLIENT" pill under the logo
    "name_in": STORY[0] + 0.35,                      # name card on the founder's first (medium) shot
    "name_out": (lambda r: r["out_start"] + r["duration"] - 0.08)(next(r for r in RANGES if r["beat"] == "STORY")),
    "cta_btn": cta_w["lien"] - 0.08,                 # button on "le lien", arrow on "اللي تحت (la vidéo)"
    "cta_arrow": cta_w["تحت"],
    "cta_30": cta_w["30"],                           # "30 secondes" lights up
}
(HERE / "events.js").write_text("window.EV = " + json.dumps(EV, ensure_ascii=False, indent=1) + ";\n", encoding="utf-8")
print(json.dumps({k: round(v, 2) for k, v in EV.items() if isinstance(v, (int, float))}, ensure_ascii=False))
for ln in LINES:
    print(f"{ln['start']:6.2f}-{ln['end']:6.2f} {'*' if ln['key'] else 'Q' if ln['q'] else ' '} " + " ".join(x["t"] for x in ln["words"]))
