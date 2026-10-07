"""Cut list for the Gzenaya vision-test reel -> edl.json + timeline.json.

  HOOK (C2430 take 1) > HOW (C2437 instructions) > TEST (silent: the chart
  fills the screen, right eye then left eye) > CTA (C2438 comment ask)

KEEP lists the spoken passages (source seconds, first word start -> last word
end). Inside each passage everything that is not speech is cut down to POST
after the voice stops + PRE before it restarts: dead air, breaths, lip noise.
"Speech" per 10 ms frame = the lav is above -31 dB and either Silero VAD says
speech or the sound is voiced (edit/vad_probs.py, edit/fillers.py).
TEST is a pad range: the picture holds the last frame of HOW under the
full-screen chart, the audio is silent (SFX carry it).

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
MIN_PAUSE = 0.12    # non-speech runs longer than this are cut
PRE, POST = 0.04, 0.06
ENERGY_DB = -31.0   # below this the lav is room tone / breath floor
MIN_RANGE = 0.40    # shorter ranges are joined to their closest neighbour (no 0.3 s framing flickers)
CLIPS = ("C2430", "C2437", "C2438")

# (beat, clip, first word start, last word end) in source seconds
KEEP = [
    ("HOOK", "C2430", 1.46, 6.49),   # شوف، فقل من 10 ثواني، هاد le test كافي باش تعرف واش عندك نقص النظر (take 1)
    ("HOW",  "C2437", 2.16, 8.21),   # غاتبان ليكم واحد التصويرة لتحت ... وغيبانولك واحد les E
    ("HOW",  "C2437", 9.76, 19.24),  # خاصك تقولنا الاتجاه ديالهم ... تديتيكطي ربعة ديال les E  (repeat "هادوك les E" cut)
    ("CTA",  "C2438", 0.92, 4.60),   # ف commentaire تقدر تقول لينا شحال شفتي من اتجاه فكل عين
]
ORDER = ["HOOK", "HOW", "TEST", "CTA"]
TEST_DUR = 8.5      # right eye 3.6 s, switch, left eye 3.6 s
CTA_TAIL = 0.6      # after the last word: the loop transition back to the hook card
HOLD: dict = {}


def speech_mask(clip: str) -> np.ndarray:
    d = np.load(AUD / f"{clip}.npz")
    e, v = d["energy"], d["voicing"]
    vad = np.load(AUD / f"{clip}_vad.npy")
    n = min(len(e), len(vad))
    e, v, vad = e[:n], v[:n], vad[:n]
    keep = (e > ENERGY_DB) & ((vad >= 0.5) | (v > 0.6))
    for a, b in HOLD.get(clip, []):
        keep[int(a * 100):int(b * 100)] = True
    return keep


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


def passage_ranges(beat: str, clip: str, a: float, b: float, words: list[dict], keep: np.ndarray) -> list[dict]:
    walls = [(w["start"], w["end"]) for w in words if w["end"] <= a - 0.005 or w["start"] >= b + 0.005]
    lo = max([en for st, en in walls if en <= a + 1e-6] + [0.0])
    hi = min([st for st, en in walls if st >= b - 1e-6] + [len(keep) / 100])
    s = a - PRE
    while s - 0.01 > lo + 0.02 and s > a - PRE - 0.10 and keep[int((s - 0.01) * 100)]:
        s -= 0.01
    t = b + POST
    while t + 0.01 < hi - 0.02 and t < b + POST + 0.20 and keep[int(t * 100)]:
        t += 0.01
    s, t = max(s, lo + 0.02), min(t, hi - 0.02)
    pieces, cur = [], s
    for qa, qb in nonspeech_runs(keep, s, t):
        if qa - cur < 0.03:                       # passage opens on non-speech: trim it
            cur = max(cur, qb - PRE)
            continue
        if t - qb < 0.03:                         # passage ends on non-speech: keep POST of it
            t = min(t, qa + POST) if beat != "CTA" else t
            continue
        pieces.append((cur, qa + POST))
        cur = qb - PRE
    pieces.append((cur, t))
    return [{"beat": beat, "source": clip, "f0": int(np.floor(ps * FPS)), "f1": int(np.ceil(pt * FPS))}
            for ps, pt in pieces if pt - ps > 0.04]


def build(words: dict, keeps: dict) -> None:
    passages = sorted(KEEP, key=lambda k: ORDER.index(k[0]))
    ranges = []
    for beat in ORDER:
        if beat == "TEST":
            ranges.append({"beat": "TEST", "source": "PAD", "f0": 0, "f1": round(TEST_DUR * FPS)})
            continue
        for b_, clip, a, b in passages:
            if b_ == beat:
                ranges += passage_ranges(beat, clip, a, b + (CTA_TAIL if beat == "CTA" else 0), words[clip], keeps[clip])
    merged = [ranges[0]]
    for r in ranges[1:]:
        m = merged[-1]
        if r["source"] == m["source"] != "PAD" and r["beat"] == m["beat"] and r["f0"] <= m["f1"] + 2:
            m["f1"] = max(m["f1"], r["f1"])
        else:
            merged.append(r)
    # join ranges shorter than MIN_RANGE to the nearest same-source neighbour (the small gap comes back)
    while True:
        short = [i for i, r in enumerate(merged) if (r["f1"] - r["f0"]) / FPS < MIN_RANGE]
        done = True
        for i in short:
            nb = []
            for j in (i - 1, i + 1):
                if 0 <= j < len(merged) and merged[j]["source"] == merged[i]["source"] != "PAD" and merged[j]["beat"] == merged[i]["beat"]:
                    gap = merged[i]["f0"] - merged[j]["f1"] if j < i else merged[j]["f0"] - merged[i]["f1"]
                    if gap / FPS <= 0.35:
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
        n = r["f1"] - r["f0"]
        out_ranges.append({"beat": r["beat"], "source": r["source"], "src_start": r["f0"] / FPS,
                           "src_end": r["f1"] / FPS, "frames": n, "out_start": t_out / FPS, "duration": n / FPS})
        if r["source"] == "PAD":
            out_ranges[-1].update({"src_start": None, "src_end": None})
        t_out += n

    def to_out(clip: str, beat: str, src: float) -> float:
        rs = [r for r in out_ranges if r["source"] == clip and r["beat"] == beat]
        for r in rs:
            if src < r["src_start"]:
                return r["out_start"]
            if src <= r["src_end"]:
                return r["out_start"] + src - r["src_start"]
        return rs[-1]["out_start"] + rs[-1]["duration"]

    out_words = []
    for beat, clip, a, b in passages:
        for w in words[clip]:
            if w["start"] >= a - 0.005 and w["end"] <= b + 0.005:
                out_words.append({"id": f"{clip}@{w['start']:.2f}", "word": w["word"], "beat": beat, "src": w["start"],
                                  "start": round(to_out(clip, beat, w["start"]), 3),
                                  "end": round(to_out(clip, beat, w["end"]), 3)})
    total = t_out / FPS
    out = EDIT
    (out / "timeline.json").write_text(json.dumps(
        {"fps": FPS, "duration": total, "width": 1080, "height": 1920,
         "ranges": out_ranges, "words": out_words}, ensure_ascii=False, indent=1), encoding="utf-8")
    (out / "edl.json").write_text(json.dumps({
        "version": 2,
        "sources": {c: str(SRC / f"{c}.MP4") for c in sorted({r["source"] for r in out_ranges} - {"PAD"})},
        "ranges": [{"source": r["source"], "start": r["src_start"], "end": r["src_end"], "beat": r["beat"]}
                   for r in out_ranges if r["source"] != "PAD"],
        "pads": [{"beat": r["beat"], "out_start": r["out_start"], "duration": r["duration"]} for r in out_ranges if r["source"] == "PAD"],
        "total_duration_s": total,
    }, indent=1), encoding="utf-8")
    spoken = sum(b - a for bt, _, a, b in passages)
    print(f"{len(out_ranges)} ranges, {len(out_words)} words, {total:.2f}s (passages {spoken:.1f}s)")
    if "-v" in sys.argv:
        for i, r in enumerate(out_ranges):
            ws = "" if r["source"] == "PAD" else " ".join(
                w["word"] for w in out_words if w["beat"] == r["beat"] and r["src_start"] - 0.03 <= w["src"] < r["src_end"])
            src_txt = f"{r['src_start']:6.2f}-{r['src_end']:6.2f}" if r["source"] != "PAD" else " " * 13
            print(f"  {i:2d} {r['out_start']:6.2f}-{r['out_start'] + r['duration']:6.2f} {r['beat']:5} "
                  f"{r['source']:5} {src_txt}  {ws}")


def main() -> None:
    words = {c: load_words(c) for c in CLIPS}
    keeps = {c: speech_mask(c) for c in CLIPS}
    build(words, keeps)


if __name__ == "__main__":
    main()
