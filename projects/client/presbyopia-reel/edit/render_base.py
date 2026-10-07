"""Base picture for the presbyopia reel: 4K source -> 9:16 -> grade -> follow-cam + zoom -> 1080x1920 @ 50 fps.

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

This reel's look ("smooth"): speed-ramped silent hook (ranges with "speed",
frames blended below 1x), a zoom-through transition between beats (the outgoing
shot pushes in and blurs, the incoming one settles from a push), and gentle
alternating framing with a slow push-in on the breath cuts inside a beat.
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
GRADE = "eq=contrast=1.045:saturation=1.06:gamma=0.985"
Z_OFFSET = 0.10                          # room for the follow-cam to pan
FACE_TARGET = (0.50, 0.40)               # where the eyes sit in the output frame (y: see plan())
FOLLOW = 0.85                            # 1 = locked on the face, 0 = fixed framing
SMOOTH_S = 0.35                          # follow-cam smoothing (Gaussian sigma, seconds)

# Framing: every range alternates between these zooms (+ a slow drift), unless
# OVERRIDE gives it keys. Keys are (t, z) or (t, z, eye_y): t = local seconds,
# "end", or ("w", src[, offset]) = that word's start in the range.
AUTO_Z = [1.00, 1.12]
DRIFT = 0.04
EYE_Y = 0.40                             # default eye line (fraction of the output height)
LOW = 0.53                               # eye line while a big graphic sits above his head


def rng(clip: str, src: float) -> int | None:
    return next((i for i, r in enumerate(TL["ranges"]) if r["source"] == clip and r["src_start"] - 0.02 <= src < r["src_end"]), None)


def beat_ranges(beat: str) -> list[int]:
    return [i for i, r in enumerate(TL["ranges"]) if r["beat"] == beat]


OVERRIDE: dict[int, list] = {}
# silent hook: keep the camera operator's pull-back readable (light zoom, eyes a bit lower to show the arm)
for k, i in enumerate(beat_ranges("HOOK")):                 # one continuous shot: zoom carries across the speed segments
    OVERRIDE[i] = [(0, 1.00 + 0.012 * k, 0.36), ("end", 1.012 + 0.012 * k, 0.36)]
# "مشكل فالقرب": push in on the key phrase
i_adv = rng("C2449", 32.78)
if i_adv is not None:
    OVERRIDE[i_adv] = [(0, 1.00, 0.48), (("w", 32.78, -0.35), 1.03, 0.48), (("w", 32.78, 0.15), 1.10, 0.48), ("end", 1.11, 0.48)]
CUTAWAYS: list = []
XFADE = 9                                  # frames of zoom-through on each side of a beat change
XZOOM = 0.32


def build_plans() -> list[list]:
    """Every cut changes the framing: an auto range takes the next AUTO_Z level that is
    at least MIN_STEP away from where the previous range ended."""
    MIN_STEP = 0.08
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
        if prev is not None and abs(keys[0][1] - prev) < MIN_STEP and TL["ranges"][idx]["beat"] != "HOOK":
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
    t0, out_i = time.time(), 0
    for idx, r in enumerate(TL["ranges"]):
        if out_i >= total_frames:
            break
        n = min(r["frames"], total_frames - out_i)
        f0 = round(r["src_start"] * FPS)
        keys = [(resolve(r, k[0]), k[1] + Z_OFFSET, k[2] if len(k) > 2 else EYE_Y) for k in plan(idx)]
        cuts = [(max(0.0, c["from"] - r["src_start"]), min(r["duration"], c["to"] - r["src_start"]), c)
                for c in CUTAWAYS if c["clip"] == r["source"] and c["from"] < r["src_end"] and c["to"] > r["src_start"]]
        full = bool(cuts)
        dw, dh = (FW, FH) if full else (IW, IH)
        speed = r.get("speed", 1.0)
        n_src = round((r["src_end"] - r["src_start"]) * FPS)
        track = face_track(r["source"], f0, n_src + 1)
        dec = decoder(r["source"], r["src_start"], n_src + 1, dw, dh)
        buf_frames: dict[int, np.ndarray] = {}
        next_idx = 0
        prev_beat = TL["ranges"][idx - 1]["beat"] if idx > 0 else r["beat"]
        next_beat = TL["ranges"][idx + 1]["beat"] if idx + 1 < len(TL["ranges"]) else r["beat"]
        for i in range(n):
            p = min(i * speed, n_src - 1e-3)
            k = int(p)
            while next_idx <= min(k + 1, n_src):
                buf = dec.stdout.read(dw * dh * 3)
                if len(buf) < dw * dh * 3:
                    break
                buf_frames[next_idx] = np.frombuffer(buf, np.uint8).reshape(dh, dw, 3)
                next_idx += 1
            for old_k in [x for x in buf_frames if x < k]:
                del buf_frames[old_k]
            if k not in buf_frames:
                sys.exit(f"range {idx}: decoder ended at source frame {k}/{n_src}")
            frame = buf_frames[k]
            frac = p - k
            if speed < 1 and frac > 0.02 and k + 1 in buf_frames:      # slow motion: blend neighbours
                frame = cv2.addWeighted(frame, 1 - frac, buf_frames[k + 1], frac, 0)
            t = i / FPS
            fx, fy, fw = track[min(k, n_src - 1)]
            # zoom-through between beats
            xz, xb = 1.0, 0.0
            if prev_beat != r["beat"] and i < XFADE:
                q = 1 - ease_io(i / XFADE); xz, xb = 1 + XZOOM * q, 9 * q
            elif next_beat != r["beat"] and i >= n - XFADE:
                q = ease_io((i - (n - XFADE) + 1) / XFADE); xz, xb = 1 + XZOOM * q, 9 * q
            cut = next((c for a, b, c in cuts if a <= t < b), None)
            if cut:
                st = r["src_start"] + t        # drift runs on source time, so it carries across a cut
                z = cut["zoom"] * (1 + cut["drift"] * ease_io((st - cut["from"]) / (cut["to"] - cut["from"])))
                cx, cy = (fx, fy) if cut["on"] == "face" else cut["on"]
                x0, y0, w = window(cx, cy, z, (0.5, 0.5))
                src = frame
            else:
                z, ey = zoom_at(keys, t)
                x0, y0, w = window(fx, fy, z * xz, (FACE_TARGET[0], ey))
                if full:
                    src = cv2.resize(frame, (IW, IH), interpolation=cv2.INTER_AREA)
                else:
                    src = frame
            out = cv2.warpAffine(src, affine(x0, y0, w, src.shape[1], src.shape[0]), (OW, OH), flags=cv2.INTER_CUBIC,
                                 borderMode=cv2.BORDER_REFLECT)
            out = sharpen(out, 0.45 if cut else 0.35)
            if xb > 0.3:
                out = cv2.GaussianBlur(out, (0, 0), xb)
            enc.stdin.write(out.tobytes())

            matte_path = TRACK / r["source"] / f"{f0 + min(k, n_src - 1):06d}.png"
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
