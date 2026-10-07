"""Find fillers ("euh", "aah", "mmm"), breaths and dead air inside the kept passages.

Per 10 ms frame of the lav channel: energy (dB), voicing (normalized
autocorrelation peak for a 70-400 Hz pitch) and zero-crossing rate.
  - breath: above the silence floor, unvoiced and noise-like, away from words
  - filler candidate: voiced sound in a gap between aligned words, away from word edges
  - long word: a word stretched past 0.6 s (a hesitation inside a word)
Writes edit/analysis_audio/candidates.json and spectrogram strips (one per
candidate, with 0.4 s of context) to check by eye: fillers show flat, steady
formant bands; real words show moving formants and consonant bursts.

    studio/.venv/bin/python edit/fillers.py
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import numpy as np

EDIT = Path(__file__).resolve().parent
SRC = EDIT.parent / "source"
OUT = EDIT / "analysis_audio"
SR, HOP, WIN = 16000, 160, 480
EDGE = 0.06          # frames this close to a word edge belong to the word


def load(clip: str) -> np.ndarray:
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(SRC / f"{clip}.MP4"), "-map", "0:a:0",
                          "-af", "pan=mono|c0=c0", "-ar", str(SR), "-f", "s16le", "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.int16).astype(np.float32) / 32768


def features(x: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """energy (dB, 10 ms), voicing (0..1, 30 ms window), zero-crossing rate per 10 ms frame."""
    n = len(x) // HOP - 3
    frames = x[: n * HOP].reshape(n, HOP)
    energy = 20 * np.log10(np.sqrt((frames ** 2).mean(axis=1)) + 1e-9)
    voicing, zcr = np.zeros(n), np.zeros(n)
    lo, hi = SR // 400, SR // 70
    for i in range(n):
        f = x[i * HOP: i * HOP + WIN]
        f = f - f.mean()
        zcr[i] = np.mean(np.abs(np.diff(np.sign(f)))) / 2
        spec = np.fft.rfft(f, 1024)
        ac = np.fft.irfft(np.abs(spec) ** 2)[:hi + 1]
        if ac[0] > 1e-8:
            voicing[i] = ac[lo:hi].max() / ac[0]
    return energy, voicing, zcr


def runs(mask: np.ndarray, min_len: int) -> list[tuple[int, int]]:
    out, s = [], None
    for k, v in enumerate(np.append(mask, False)):
        if v and s is None:
            s = k
        elif not v and s is not None:
            if k - s >= min_len:
                out.append((s, k))
            s = None
    return out


def spectro_strip(x: np.ndarray, a: float, b: float, words: list[dict], path: Path, title: str) -> None:
    import cv2
    a0, b0 = max(0.0, a - 0.4), b + 0.4
    seg = x[int(a0 * SR): int(b0 * SR)]
    n = max(1, (len(seg) - 512) // 80)
    spec = np.stack([np.abs(np.fft.rfft(seg[i * 80: i * 80 + 512] * np.hanning(512)))[:200] for i in range(n)], 1)
    img = np.clip((20 * np.log10(spec + 1e-6) + 80) / 70 * 255, 0, 255).astype(np.uint8)[::-1]
    img = cv2.applyColorMap(cv2.resize(img, (n * 2, 300)), cv2.COLORMAP_MAGMA)
    px = lambda t: int((t - a0) / (b0 - a0) * img.shape[1])  # noqa: E731
    cv2.rectangle(img, (px(a), 0), (px(b), 299), (255, 255, 255), 2)
    canvas = np.zeros((360, img.shape[1], 3), np.uint8)
    canvas[30:330] = img
    for w in words:
        if w["end"] > a0 and w["start"] < b0:
            cv2.line(canvas, (px(w["start"]), 330), (px(w["start"]), 345), (0, 255, 0), 2)
            cv2.putText(canvas, w["word"].encode("ascii", "replace").decode()[:8], (px(w["start"]) + 2, 356),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 0), 1)
    cv2.putText(canvas, title, (4, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1)
    cv2.imwrite(str(path), canvas)


def main() -> None:
    sys.path.insert(0, str(EDIT))
    from cut import KEEP  # noqa: E402
    OUT.mkdir(exist_ok=True)
    cands = []
    for clip in sorted({c for _, c, _, _ in KEEP}):
        x = load(clip)
        e, v, z = features(x)
        np.savez_compressed(OUT / f"{clip}.npz", energy=e, voicing=v, zcr=z)
        words = json.loads((EDIT / "darija" / f"{clip}.words.json").read_text())
        inword = np.zeros(len(e), bool)
        for w in words:
            inword[max(0, int((w["start"] - EDGE) * 100)):int((w["end"] + EDGE) * 100) + 1] = True
        for beat, c, a, b in KEEP:
            if c != clip:
                continue
            i0, i1 = int(a * 100), int(b * 100)
            seg = slice(i0, i1)
            loud = e[seg] > -42
            voiced = loud & (v[seg] > 0.55) & (e[seg] > -36)
            gap = ~inword[seg]
            found = []
            for s, t in runs(gap & voiced, 8):           # >= 80 ms voiced, outside words: filler?
                found.append(("voiced", s, t))
            for s, t in runs(gap & loud & ~voiced, 10):  # >= 100 ms noise-like, outside words: breath
                found.append(("breath", s, t))
            for kind, s, t in found:
                cands.append({"clip": clip, "beat": beat, "kind": kind, "start": (i0 + s) / 100, "end": (i0 + t) / 100,
                              "db": round(float(e[i0 + s:i0 + t].max()), 1),
                              "voicing": round(float(v[i0 + s:i0 + t].mean()), 2),
                              "zcr": round(float(z[i0 + s:i0 + t].mean()), 2)})
            for w in words:
                if w["start"] >= a - 0.005 and w["end"] <= b + 0.005 and w["end"] - w["start"] > 0.6:
                    cands.append({"clip": clip, "beat": beat, "kind": "long_word", "start": w["start"], "end": w["end"],
                                  "word": w["word"]})
        for k, cnd in enumerate(c for c in cands if c["clip"] == clip and c["kind"] != "breath"):
            spectro_strip(x, cnd["start"], cnd["end"], words, OUT / f"{clip}_{cnd['start']:06.2f}.png",
                          f"{clip} {cnd['kind']} {cnd['start']:.2f}-{cnd['end']:.2f}")
    cands.sort(key=lambda c: (c["clip"], c["start"]))
    (OUT / "candidates.json").write_text(json.dumps(cands, ensure_ascii=False, indent=1))
    for c in cands:
        extra = c.get("word") or f"{c['db']} dB v={c['voicing']} z={c['zcr']}"
        print(f"{c['clip']} {c['beat']:5} {c['kind']:9} {c['start']:6.2f}-{c['end']:6.2f} ({c['end'] - c['start']:.2f}s) {extra}")


if __name__ == "__main__":
    main()
