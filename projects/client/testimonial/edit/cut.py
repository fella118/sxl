"""Cut list for the SOGIXEL testimonial (Dnanou Atae, Gzenaya Optique) -> edl.json + timeline.json.

  HOOK   C2406 0.0-0.6: the host's smile, eased slow motion. Its sound is
         C2408 already running (J-cut), so C2408 is one continuous track
         from the first frame.
  INTRO  C2408 from 2.85 (in sync with that track) to "خلي ليك الكلمة".
  STORY  C2410 (wide, desk + neon): other agencies / ROI > Si Saad called >
         store was slow > "des points" > agreed on the return > "جاب الله
         التيسير". Off-topic banter (0-4 s), "متفقين", the doubled "نفس",
         "هادشي اللي كاين" and the trailing "avec... صافي" are out.
  PROOF  C2411 close-up: "دابا ça fait واحد العام ... satisfait إن شاء الله"
         (the off-camera question is cut).
  CTA    IMG_6057 (iPhone selfie, 50 fps proxy) + a short hold for the end card.

Inside every passage, non-speech longer than MIN_PAUSE is cut down to POST +
PRE of air (lav level + Silero VAD + voicing). The pauses are tightened, not
removed: this is a testimonial, it should still breathe.

    studio/.venv/bin/python edit/cut.py [-v]
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
MIN_PAUSE = 0.24    # non-speech runs longer than this are cut
PRE, POST = 0.07, 0.11
ENERGY_DB = -33.0   # below this the lav is room tone / breath floor
MIN_RANGE = 0.55    # shorter ranges are joined to their closest neighbour
JOIN_GAP = 0.55     # ...when the gap that comes back is at most this long
MIN_SAVE = 0.20     # a pause cut must save at least this much, or it is not worth a jump cut
CLIPS = ("C2408", "C2410", "C2411", "IMG_6057")
PATHS = {"C2406": SRC / "C2406.MP4", "C2408": SRC / "C2408.MP4", "C2410": SRC / "C2410.MP4",
         "C2411": SRC / "C2411.MP4", "IMG_6057": EDIT / "proxy" / "IMG_6057.mov"}

HOOK = {"clip": "C2406", "a": 0.00, "b": 0.60, "speed": 0.60,     # 1.0 s of smile
        "audio": "C2408", "audio_end": 2.85}                       # C2408 sound under it, picture cuts in at 2.85
# (beat, clip, start, end) in source seconds. A start given as ("exact", t) is kept as is.
KEEP = [
    ("INTRO", "C2408", ("exact", 2.85), 14.36),            # ... monsieur Dnanou Atae ... SOGIXEL. سي Atae، نخلي ليك الكلمة
    # C2410: the cuts at exact times drop a drawn-out "euhhh" (flat harmonics in analysis_audio/C2410_*.png)
    ("STORY", "C2410", 6.50, ("exact", 9.34)),            # باختصار نعاود ليكم l'histoire ديالي مع
    ("STORY", "C2410", ("exact", 11.34), ("exact", 15.10)),  # les agences marketing. déjà كنت بديت مع
    ("STORY", "C2410", ("exact", 16.38), 21.84),          # d'autres agences ولكن المشكل ... le retour sur investissement
    ("STORY", "C2410", 23.72, ("exact", 26.99)),          # حتى جا السي سعد عيط ليا فالتيليفون، أنا déjà
    ("STORY", "C2410", ("exact", 28.03), ("exact", 30.75)),  # الماڭازان كنت بديت فيه ça fait واحد
    ("STORY", "C2410", ("exact", 31.94), 34.76),          # العام بحال هكا كانت الأمور ناعسة
    ("STORY", "C2410", ("exact", 36.76), 38.24),          # عيط ليا السي سعد حتى هو
    ("STORY", "C2410", 39.06, ("exact", 41.87)),          # الصراحة نفس الدخلة اللي كيدخلوها الناس ديال
    ("STORY", "C2410", ("exact", 43.56), ("exact", 50.34)),  # الماركوتينغ كاملين ولكن عطيتو des points ... فهاد الأمر
    ("STORY", "C2410", ("exact", 54.22), ("exact", 57.62)),  # تفاهمنا على le retour أهم حاجة عندي
    ("STORY", "C2410", ("exact", 58.58), 59.11),          # فالمڭازة
    ("STORY", "C2410", 60.73, ("exact", 61.83)),          # وجاب الله التيسير مع
    ("STORY", "C2410", ("exact", 62.34), 62.99),          # سي سعد
    ("PROOF", "C2411", 6.87, ("exact", 9.05)),            # دابا ça fait واحد العام
    ("PROOF", "C2411", ("exact", 9.92), 14.76),           # grosso modo كانريكومندي أي واحد يخدم مع سي سعد وغيكون satisfait إن شاء الله
    ("CTA", "IMG_6057", 0.00, 9.58),                      # يلا كنتي حتى نتايا عييتي ... نقدرو نعاونوك
]
CTA_TAIL = 0.50     # picture after the last word (end card)
ORDER = ["HOOK", "INTRO", "STORY", "PROOF", "CTA"]


def speech_mask(clip: str) -> np.ndarray:
    d = np.load(AUD / f"{clip}.npz")
    e, v = d["energy"], d["voicing"]
    vad = np.load(AUD / f"{clip}_vad.npy")
    n = min(len(e), len(vad))
    e, v, vad = e[:n], v[:n], vad[:n]
    return (e > ENERGY_DB) & ((vad >= 0.5) | (v > 0.6))


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


def passage_ranges(beat: str, clip: str, a, b, keep: np.ndarray, tail: float = 0.0) -> list[dict]:
    exact = isinstance(a, tuple)
    a = a[1] if exact else a
    exact_end = isinstance(b, tuple)
    b = b[1] - POST if exact_end else b         # so that b + POST is the exact end
    s = a if exact else max(0.0, a - PRE)
    t = min(b + POST + tail, len(keep) / 100)
    pieces, cur = [], s
    for qa, qb in nonspeech_runs(keep, s, b + POST):
        if qa - cur < 0.03:                       # passage opens on non-speech: trim it
            if not exact:
                cur = max(cur, qb - PRE)
            continue
        if b + POST - qb < 0.03:                  # passage ends on non-speech: keep POST of it
            if not tail and not exact_end:
                t = min(t, qa + POST)
            continue
        if (qb - qa) - (PRE + POST) < MIN_SAVE:
            continue
        pieces.append((cur, qa + POST))
        cur = qb - PRE
    pieces.append((cur, t))
    return [{"beat": beat, "source": clip, "f0": int(np.floor(ps * FPS)) if not (exact and ps == s) else round(ps * FPS),
             "f1": int(np.ceil(pt * FPS))} for ps, pt in pieces if pt - ps > 0.04]


def build(words: dict, keeps: dict) -> None:
    ranges = [{"beat": "HOOK", "source": HOOK["clip"], "f0": round(HOOK["a"] * FPS), "f1": round(HOOK["b"] * FPS),
               "speed": HOOK["speed"]}]
    for beat in ORDER[1:]:
        for b_, clip, a, b in KEEP:
            if b_ == beat:
                ranges += passage_ranges(beat, clip, a, b, keeps[clip], CTA_TAIL if beat == "CTA" else 0.0)
    merged = [ranges[0]]
    for r in ranges[1:]:
        m = merged[-1]
        if r["beat"] != "HOOK" and r["source"] == m["source"] and r["beat"] == m["beat"] and r["f0"] <= m["f1"] + 2:
            m["f1"] = max(m["f1"], r["f1"])
        else:
            merged.append(r)
    while True:                                   # no micro-ranges: give the short pause back instead
        done = True
        for i, r in enumerate(merged):
            if r["beat"] == "HOOK" or (r["f1"] - r["f0"]) / FPS >= MIN_RANGE:
                continue
            nb = []
            for j in (i - 1, i + 1):
                if 0 <= j < len(merged) and merged[j]["source"] == r["source"] and merged[j]["beat"] == r["beat"]:
                    gap = r["f0"] - merged[j]["f1"] if j < i else merged[j]["f0"] - r["f1"]
                    if 0 <= gap / FPS <= JOIN_GAP:
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
        sp = r.get("speed", 1.0)
        n = round((r["f1"] - r["f0"]) / sp)
        o = {"beat": r["beat"], "source": r["source"], "src_start": r["f0"] / FPS, "src_end": r["f1"] / FPS,
             "frames": n, "out_start": t_out / FPS, "duration": n / FPS}
        if r["beat"] == "HOOK":
            nxt = next(m for m in merged if m["beat"] == "INTRO")      # C2408's own picture picks up its sound here
            o.update({"speed": sp, "audio": {"source": HOOK["audio"], "start": round(nxt["f0"] / FPS - n / FPS, 3)}})
        out_ranges.append(o)
        t_out += n

    def to_out(clip: str, src: float) -> float | None:
        for r in out_ranges:
            au = r.get("audio")
            if au and au["source"] == clip and au["start"] - 0.005 <= src < au["start"] + r["duration"]:
                return r["out_start"] + src - au["start"]
            if "speed" not in r and r["source"] == clip and r["src_start"] - 0.005 <= src <= r["src_end"] + 0.005:
                return r["out_start"] + min(max(src - r["src_start"], 0.0), r["duration"])
        return None

    out_words = []
    for beat, clip, a, b in KEEP:
        a = a[1] if isinstance(a, tuple) else a
        b = b[1] if isinstance(b, tuple) else b
        if beat == "INTRO":
            a = HOOK["audio_end"] - out_ranges[0]["duration"]
        for w in words[clip]:
            if w["start"] >= a - 0.05 and w["end"] <= b + 0.005:
                s, e = to_out(clip, w["start"]), to_out(clip, w["end"])
                if s is None:                     # the word's start fell in a cut pause: use the next kept frame
                    nxt = [r for r in out_ranges if r["source"] == clip and r["src_start"] > w["start"]]
                    s = nxt[0]["out_start"] if nxt else None
                if s is None:
                    continue
                out_words.append({"id": f"{clip}@{w['start']:.2f}", "word": w["word"], "beat": beat, "src": w["start"],
                                  "start": round(s, 3), "end": round(e if e is not None else s + 0.2, 3)})
    total = t_out / FPS
    (EDIT / "timeline.json").write_text(json.dumps(
        {"fps": FPS, "duration": total, "width": 1080, "height": 1920,
         "ranges": out_ranges, "words": out_words}, ensure_ascii=False, indent=1), encoding="utf-8")
    (EDIT / "edl.json").write_text(json.dumps({
        "version": 2,
        "sources": {c: str(PATHS[c]) for c in sorted({r["source"] for r in out_ranges})},
        "ranges": [{"source": r["source"], "start": r["src_start"], "end": r["src_end"], "beat": r["beat"],
                    **({"speed": r["speed"], "audio": r["audio"]} if "speed" in r else {})} for r in out_ranges],
        "total_duration_s": total,
    }, indent=1), encoding="utf-8")
    print(f"{len(out_ranges)} ranges, {len(out_words)} words, {total:.2f}s")
    if "-v" in sys.argv:
        for i, r in enumerate(out_ranges):
            ws = " ".join(w["word"] for w in out_words
                          if r["out_start"] - 0.01 <= w["start"] < r["out_start"] + r["duration"] - 0.01)
            src_txt = f"{r['src_start']:6.2f}-{r['src_end']:6.2f}" + (f" x{r['speed']}" if "speed" in r else "")
            print(f"  {i:2d} {r['out_start']:6.2f}-{r['out_start'] + r['duration']:6.2f} {r['beat']:5} "
                  f"{r['source']:8} {src_txt}  {ws}")


def main() -> None:
    words = {c: load_words(c) for c in CLIPS}
    keeps = {c: speech_mask(c) for c in CLIPS}
    build(words, keeps)


if __name__ == "__main__":
    main()
