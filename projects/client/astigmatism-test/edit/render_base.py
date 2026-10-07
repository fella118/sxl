"""Base picture for the vision-test reel: 4K source -> 9:16 -> grade -> follow-cam + zoom -> 1080x1920 @ 50 fps.

Same engine as the comment-hook reel (v3):
  - Follow-cam: the crop follows the speaker's face (YuNet track from
    studio/bin/track_subject.py), smoothed zero-phase per range so the camera
    moves with him like an operator, without lag or jitter.
  - Zoom plan per range (framing change on cuts, word-anchored moves).
  - Cutaways: 4K close-ups of what he shows (warranty cards, the two frames),
    keyed on source time so they can span a cut.
  - Framing per range: alternating wide/tight on every cut, a push-in on each
    question, and a lower eye line (more headroom) while the index table, the
    lens card and the frame-arm diagram are on screen.
  - Writes mask.mkv (person matte aligned to every output frame, lossless gray)
    and facepos.json (face centre/size in output pixels) for the overlay layers.

    studio/.venv/bin/python edit/render_base.py [--until 21.0]

PAD ranges (the silent test, covered by the full-screen chart) hold the last
frame of the previous range, blurred and dimmed; their matte is empty.
Look (different from Reel 02 on purpose): warmer grade, soft vignette, slow
push-in through every range, and a 4-frame whip blur on each cut.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import cv2
import numpy as np

EDIT = Path(__file__).resolve().parent
OUT = EDIT
TL = json.loads((OUT / "timeline.json").read_text())
SRC = EDIT.parent / "source"
TRACK = EDIT / "track"
FPS = TL["fps"]
OW, OH = 1080, 1920
FW, FH = 2160, 3840                      # full-res 9:16 crop of the source
IW, IH = 1440, 2560                      # working size for normal framing (1.33x headroom)
GRADE = "eq=contrast=1.07:saturation=1.12:gamma=0.98,colorbalance=rs=0.03:bs=-0.03:rm=0.015:bm=-0.02"   # warmer than Reel 02
Z_OFFSET = 0.10                          # room for the follow-cam to pan
FACE_TARGET = (0.50, 0.40)               # where the eyes sit in the output frame (y: see plan())
FOLLOW = 0.85                            # 1 = locked on the face, 0 = fixed framing
SMOOTH_S = 0.35                          # follow-cam smoothing (Gaussian sigma, seconds)

# Framing: every range alternates between these zooms (+ a slow drift), unless
# OVERRIDE gives it keys. Keys are (t, z) or (t, z, eye_y): t = local seconds,
# "end", or ("w", src[, offset]) = that word's start in the range.
AUTO_Z = [1.02, 1.10]
DRIFT = 0.06                             # slow push-in through every range (Reel 02: 0.03)
EYE_Y = 0.40                             # default eye line (fraction of the output height)
LOW = 0.53                               # eye line while a big graphic sits above his head


def rng(clip: str, src: float) -> int | None:
    return next((i for i, r in enumerate(TL["ranges"]) if r["source"] == clip and r["src_start"] - 0.02 <= src < r["src_end"]), None)


def beat_ranges(beat: str) -> list[int]:
    return [i for i, r in enumerate(TL["ranges"]) if r["beat"] == beat]


OVERRIDE: dict[int, list] = {}
OVERRIDE[0] = [(0, 1.24), (0.3, 1.10)]                                   # "شوف!" punch
# HOW: the step pictograms sit above his head -> lower eye line for the whole beat
for k, i in enumerate(beat_ranges("HOW")):
    z = [1.00, 1.08][k % 2]
    OVERRIDE[i] = [(0, z, LOW), ("end", z + 0.06, LOW)]
# "غانغمضو عين": push in on him covering his eye
i_eye = rng("C2437", 15.40)
if i_eye is not None:
    OVERRIDE[i_eye] = [(0, 1.06, LOW), (("w", 15.40, -0.3), 1.06, LOW), (("w", 15.40, 0.2), 1.16, LOW), ("end", 1.18, LOW)]
    for i in beat_ranges("HOW"):
        if i > i_eye:                        # he leans in after covering his eye: keep it wide under the panel
            OVERRIDE[i] = [(0, 1.00 if (i - i_eye) % 2 else 1.04, LOW), ("end", 1.04 if (i - i_eye) % 2 else 1.08, LOW)]

# no cutaways in this reel
CUTAWAYS: list = []


def build_plans() -> list[list]:
    """Every cut changes the framing: an auto range takes the next AUTO_Z level that is
    at least MIN_STEP away from where the previous range ended."""
    MIN_STEP = 0.05                       # the whip blur carries the cut
    plans, prev, k = [], None, 0
    for idx in range(len(TL["ranges"])):
        if idx in OVERRIDE:
            keys = OVERRIDE[idx]
        else:
            for _ in range(len(AUTO_Z)):
                z = AUTO_Z[k % len(AUTO_Z)]
                k += 1
                if prev is None or abs(z - prev) >= MIN_STEP:
                    break
            keys = [(0, z), ("end", z + DRIFT)]
        if prev is not None and abs(keys[0][1] - prev) < MIN_STEP:
            print(f"  note: range {idx} starts {keys[0][1]:.2f} after {prev:.2f} (small framing change)")
        plans.append(keys)
        prev = keys[-1][1]
    return plans


PLANS = build_plans()


def plan(idx: int) -> list:
    return PLANS[idx]


def ease_io(x: float) -> float:
    return 4 * x ** 3 if x < 0.5 else 1 - (-2 * x + 2) ** 3 / 2


def zoom_at(keys: list[tuple[float, float, float]], t: float) -> tuple[float, float]:
    if t <= keys[0][0]:
        return keys[0][1], keys[0][2]
    for (t0, z0, y0), (t1, z1, y1) in zip(keys, keys[1:]):
        if t <= t1:
            k = ease_io((t - t0) / max(t1 - t0, 1e-6))
            return z0 + (z1 - z0) * k, y0 + (y1 - y0) * k
    return keys[-1][1], keys[-1][2]


def word_time(r: dict, src: float) -> float:
    hit = next(x for x in TL["words"] if abs(x["src"] - src) < 0.03 and x["id"].startswith(r["source"]))
    return hit["start"] - r["out_start"]


def resolve(r: dict, k) -> float:
    if k == "end":
        return r["duration"]
    if isinstance(k, tuple):
        return word_time(r, k[1]) + (k[2] if len(k) > 2 else 0)
    return float(k)


def face_track(clip: str, f0: int, n: int) -> np.ndarray:
    """Smoothed (cx, cy, w) per frame of a range, normalized to the 9:16 frame."""
    faces = json.loads((TRACK / f"{clip}.faces.json").read_text())
    pad = int(SMOOTH_S * FPS * 3)
    idx = np.arange(f0 - pad, f0 + n + pad)
    raw = np.array([faces.get(str(i), [np.nan] * 5)[:3] for i in idx], dtype=float)
    for c in range(3):                     # fill gaps (no face found) by interpolation
        col = raw[:, c]
        ok = ~np.isnan(col)
        col[~ok] = np.interp(np.flatnonzero(~ok), np.flatnonzero(ok), col[ok]) if ok.any() else 0.5
    sigma = SMOOTH_S * FPS
    k = np.exp(-0.5 * (np.arange(-3 * sigma, 3 * sigma + 1) / sigma) ** 2)
    k /= k.sum()
    sm = np.stack([np.convolve(np.pad(raw[:, c], (len(k) // 2,), mode="edge"), k, mode="valid") for c in range(3)], 1)
    sm = sm[pad:pad + n]
    mean = sm.mean(axis=0)
    sm[:, :2] = mean[:2] + FOLLOW * (sm[:, :2] - mean[:2])
    return sm


def window(fx: float, fy: float, z: float, target=FACE_TARGET) -> tuple[float, float, float]:
    w = 1 / z
    x0 = min(max(fx - target[0] * w, 0.0), 1 - w)
    y0 = min(max(fy - target[1] * w, 0.0), 1 - w)
    return x0, y0, w


def affine(x0: float, y0: float, w: float, iw: int, ih: int) -> np.ndarray:
    """Map the normalized window (x0, y0, w) of an iw x ih image onto the output frame."""
    sx, sy = OW / (w * iw), OH / (w * ih)
    return np.float32([[sx, 0, -x0 * iw * sx], [0, sy, -y0 * ih * sy]])


def decoder(clip: str, start: float, n: int, w: int, h: int) -> subprocess.Popen:
    vf = f"crop={FW}:{FH}:0:128,scale={w}:{h}:flags=lanczos,{GRADE},format=bgr24"
    return subprocess.Popen(
        ["ffmpeg", "-nostdin", "-v", "error", "-ss", f"{start:.3f}", "-i", str(SRC / f"{clip}.MP4"),
         "-frames:v", str(n), "-vf", vf, "-f", "rawvideo", "-pix_fmt", "bgr24", "-"],
        stdout=subprocess.PIPE, stdin=subprocess.DEVNULL, bufsize=w * h * 3 * 2)


WHIP = [46, 30, 16, 7]                   # horizontal blur (px) on the first frames after a cut
_yy, _xx = np.mgrid[0:OH, 0:OW].astype(np.float32)
VIGNETTE = (1 - 0.32 * np.clip((((_xx - OW / 2) / (OW * 0.62)) ** 2 + ((_yy - OH * 0.45) / (OH * 0.62)) ** 2) - 0.25, 0, 1))[..., None]


def whip(img: np.ndarray, k: int, direction: int) -> np.ndarray:
    """Directional smear for the first frames after a cut (alternating left/right)."""
    kern = np.zeros((1, k), np.float32)
    kern[0, : k // 2 + 1] = np.linspace(1, 0.2, k // 2 + 1) if direction > 0 else np.linspace(0.2, 1, k // 2 + 1)
    kern /= kern.sum()
    return cv2.filter2D(img, -1, kern, borderType=cv2.BORDER_REFLECT)


def sharpen(img: np.ndarray, amount: float = 0.35) -> np.ndarray:
    blur = cv2.GaussianBlur(img, (0, 0), 1.1)
    return cv2.addWeighted(img, 1 + amount, blur, -amount, 0)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("-o", "--output", type=Path, default=OUT / "base.mp4")
    ap.add_argument("--until", type=float, default=None, help="Stop at this output time (samples)")
    ap.add_argument("--crf", type=int, default=12)
    args = ap.parse_args()

    total_frames = round(TL["duration"] * FPS)
    if args.until:
        total_frames = min(total_frames, round(args.until * FPS))
    enc = subprocess.Popen(
        ["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{OW}x{OH}",
         "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "fast", "-crf", str(args.crf),
         "-pix_fmt", "yuv420p", "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709",
         str(args.output)], stdin=subprocess.PIPE)
    menc = subprocess.Popen(
        ["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "gray", "-s", f"{OW}x{OH}",
         "-r", str(FPS), "-i", "-", "-c:v", "ffv1", str(args.output.with_name("mask.mkv"))], stdin=subprocess.PIPE)

    facepos: list = []
    last_out = None
    t0, out_i = time.time(), 0
    for idx, r in enumerate(TL["ranges"]):
        if out_i >= total_frames:
            break
        n = min(r["frames"], total_frames - out_i)
        if r["source"] == "PAD":
            held = cv2.GaussianBlur(last_out, (0, 0), 28) * 0.55 if last_out is not None else np.zeros((OH, OW, 3))
            held = held.astype(np.uint8).tobytes()
            empty = np.zeros((OH, OW), np.uint8).tobytes()
            for _ in range(n):
                enc.stdin.write(held)
                menc.stdin.write(empty)
                facepos.append(None)
                out_i += 1
            print(f"  range {idx:2d} PAD    {n:4d} frames (held)", flush=True)
            continue
        f0 = round(r["src_start"] * FPS)
        keys = [(resolve(r, k[0]), k[1] + Z_OFFSET, k[2] if len(k) > 2 else EYE_Y) for k in plan(idx)]
        cuts = [(max(0.0, c["from"] - r["src_start"]), min(r["duration"], c["to"] - r["src_start"]), c)
                for c in CUTAWAYS if c["clip"] == r["source"] and c["from"] < r["src_end"] and c["to"] > r["src_start"]]
        full = bool(cuts)
        dw, dh = (FW, FH) if full else (IW, IH)
        track = face_track(r["source"], f0, n)
        dec = decoder(r["source"], r["src_start"], n, dw, dh)
        for i in range(n):
            buf = dec.stdout.read(dw * dh * 3)
            if len(buf) < dw * dh * 3:
                sys.exit(f"range {idx}: decoder ended at frame {i}/{n}")
            frame = np.frombuffer(buf, np.uint8).reshape(dh, dw, 3)
            t = i / FPS
            fx, fy, fw = track[i]
            cut = next((c for a, b, c in cuts if a <= t < b), None)
            if cut:
                st = r["src_start"] + t        # drift runs on source time, so it carries across a cut
                z = cut["zoom"] * (1 + cut["drift"] * ease_io((st - cut["from"]) / (cut["to"] - cut["from"])))
                cx, cy = (fx, fy) if cut["on"] == "face" else cut["on"]
                x0, y0, w = window(cx, cy, z, (0.5, 0.5))
                src = frame
            else:
                z, ey = zoom_at(keys, t)
                x0, y0, w = window(fx, fy, z, (FACE_TARGET[0], ey))
                if full:
                    src = cv2.resize(frame, (IW, IH), interpolation=cv2.INTER_AREA)
                else:
                    src = frame
            out = cv2.warpAffine(src, affine(x0, y0, w, src.shape[1], src.shape[0]), (OW, OH), flags=cv2.INTER_CUBIC,
                                 borderMode=cv2.BORDER_REFLECT)
            last_out = sharpen(out, 0.45 if cut else 0.35)
            if idx > 0 and i < len(WHIP) and TL["ranges"][idx - 1]["source"] != "PAD":
                last_out = whip(last_out, WHIP[i], 1 if idx % 2 else -1)
            last_out = (last_out * VIGNETTE).astype(np.uint8)
            enc.stdin.write(last_out.tobytes())

            matte_path = TRACK / r["source"] / f"{f0 + i:06d}.png"
            matte = cv2.imread(str(matte_path), cv2.IMREAD_GRAYSCALE)
            if matte is None:
                sys.exit(f"missing matte {matte_path} (run studio/bin/track_subject.py)")
            m = cv2.warpAffine(matte, affine(x0, y0, w, matte.shape[1], matte.shape[0]), (OW, OH), flags=cv2.INTER_LINEAR,
                               borderMode=cv2.BORDER_REPLICATE)
            menc.stdin.write(m.tobytes())
            # face in output pixels for every frame (cutaways included, so safety checks see them)
            facepos.append([round((fx - x0) / w * OW, 1), round((fy - y0) / w * OH, 1), round(fw / w * OW, 1)])
            out_i += 1
        dec.stdout.close()
        dec.wait()
        print(f"  range {idx:2d} {r['beat']:6} {n:4d} frames{' +cutaway' if cuts else ''}  "
              f"({out_i / (time.time() - t0):.1f} fps)", flush=True)
    enc.stdin.close(); menc.stdin.close()
    enc.wait(); menc.wait()
    (OUT / "facepos.json").write_text(json.dumps({"fps": FPS, "frames": facepos}))
    (EDIT / "animations" / "overlay" / "facepos.js").write_text(
        "window.FACE = " + json.dumps({"fps": FPS, "frames": facepos}) + ";\n")
    print(f"wrote {args.output}, mask.mkv, facepos ({out_i} frames, {out_i / FPS:.2f}s) in {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
