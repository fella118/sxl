"""Base picture: 4K source -> 9:16 -> grade -> follow-cam + zoom -> 1080x1920 @ 50 fps.

v3:
  - Follow-cam: the crop follows the speaker's face (YuNet track from
    studio/bin/track_subject.py), smoothed zero-phase per range so the camera
    moves with him like an operator, without lag or jitter.
  - Zoom plan per range (framing change on cuts, word-anchored moves).
  - Cutaways: detail shots of the same moment (glasses, sign) cropped from the
    full 4K frame so they stay sharp.
  - Writes mask.mkv (person matte aligned to every output frame, lossless gray)
    and facepos.json (face centre/size in output pixels) for the overlay layers.

    studio/.venv/bin/python edit/render_base.py [--until 21.0] [-o edit/base.mp4]
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

import cv2
import numpy as np

EDIT = Path(__file__).resolve().parent
TL = json.loads((EDIT / "timeline.json").read_text())
SRC = EDIT.parent / "source"
TRACK = EDIT / "track"
FPS = TL["fps"]
OW, OH = 1080, 1920
FW, FH = 2160, 3840                      # full-res 9:16 crop of the source
IW, IH = 1440, 2560                      # working size for normal framing (1.33x headroom)
GRADE = "eq=contrast=1.045:saturation=1.06:gamma=0.985"
Z_OFFSET = 0.10                          # room for the follow-cam to pan
FACE_TARGET = (0.50, 0.40)               # where the eyes sit in the output frame
FOLLOW = 0.85                            # 1 = locked on the face, 0 = fixed framing
SMOOTH_S = 0.35                          # follow-cam smoothing (Gaussian sigma, seconds)

# Zoom plan per range (index in timeline.json). Keys: (t, z) with t = local
# seconds, "end", or ("w", src_time[, offset]) = a word's start in that range.
PLAN = {
    0: [(0, 1.00), ("end", 1.04)],
    1: [(0, 1.04), ("end", 1.09)],
    2: [(0, 1.24), ("end", 1.27)],                                     # bien sûr
    3: [(0, 1.04), ("end", 1.07)],
    4: [(0, 1.16), ("end", 1.20)],
    5: [(0, 1.04), ("end", 1.05)],
    6: [(0, 1.14), ("end", 1.16)],                                     # plus 1 / plus 2
    7: [(0, 1.23), ("end", 1.26)],                                     # مايسباريوش
    8: [(0, 1.03), (("w", 22.63, -0.2), 1.05), (("w", 23.97), 1.13), ("end", 1.14)],
    9: [(0, 1.14), (("w", 25.83, -0.45), 1.16), (("w", 25.83), 1.27), ("end", 1.28)],   # plus 3
    10: [(0, 1.25), (("w", 29.25, -0.5), 1.27), (("w", 29.25), 1.02), ("end", 1.04)],    # critères
    11: [(0, 1.11), ("end", 1.13)],
    12: [(0, 1.03), ("end", 1.05)],
    13: [(0, 1.14), ("end", 1.18)],
    14: [(0, 1.24), ("end", 1.25)],                                    # يلا
    15: [(0, 1.25), ("end", 1.27)],                                    # ماولفتيهمش (glued)
    16: [(0, 1.06), ("end", 1.07)],
    17: [(0, 1.07), ("end", 1.08)],                                    # تلتيام (glued)
    18: [(0, 1.14), (("w", 49.59, -0.45), 1.16), (("w", 49.59), 1.27), ("end", 1.28)],  # le professionnel
    19: [(0, 1.02), ("end", 1.20)],                                    # CTA push-in
}

# Cutaways: detail of the same moment. from/to are word anchors (src time) or
# (src, offset); "on" = "face" follows the eyes, else a fixed point (x, y) of the 9:16 frame.
CUTAWAYS = [
    {"range": 8, "from": 0.0, "to": ("w", 20.61, -0.12), "on": "face", "zoom": 2.4, "drift": 0.10},   # les mesures -> glasses ECU
    {"range": 18, "from": ("w", 46.50, -0.05), "to": ("w", 47.12, -0.05), "on": (0.47, 0.13), "zoom": 1.7, "drift": 0.06},  # ترجع عندنا -> sign
]


def ease_io(x: float) -> float:
    return 4 * x ** 3 if x < 0.5 else 1 - (-2 * x + 2) ** 3 / 2


def zoom_at(keys: list[tuple[float, float]], t: float) -> float:
    if t <= keys[0][0]:
        return keys[0][1]
    for (t0, z0), (t1, z1) in zip(keys, keys[1:]):
        if t <= t1:
            return z0 + (z1 - z0) * ease_io((t - t0) / max(t1 - t0, 1e-6))
    return keys[-1][1]


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
    ap.add_argument("-o", "--output", type=Path, default=EDIT / "base.mp4")
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
        keys = [(resolve(r, k), z + Z_OFFSET) for k, z in PLAN[idx]]
        cuts = [(resolve(r, c["from"]), resolve(r, c["to"]), c) for c in CUTAWAYS if c["range"] == idx]
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
                a, b, _ = next(x for x in cuts if x[2] is cut)
                z = cut["zoom"] * (1 + cut["drift"] * ease_io((t - a) / max(b - a, 1e-6)))
                cx, cy = (fx, fy) if cut["on"] == "face" else cut["on"]
                x0, y0, w = window(cx, cy, z, (0.5, 0.5))
                src = frame
            else:
                z = zoom_at(keys, t)
                x0, y0, w = window(fx, fy, z)
                if full:
                    src = cv2.resize(frame, (IW, IH), interpolation=cv2.INTER_AREA)
                else:
                    src = frame
            out = cv2.warpAffine(src, affine(x0, y0, w, src.shape[1], src.shape[0]), (OW, OH), flags=cv2.INTER_CUBIC,
                                 borderMode=cv2.BORDER_REFLECT)
            enc.stdin.write(sharpen(out, 0.45 if cut else 0.35).tobytes())

            matte_path = TRACK / r["source"] / f"{f0 + i:06d}.png"
            matte = cv2.imread(str(matte_path), cv2.IMREAD_GRAYSCALE)
            if matte is None:
                sys.exit(f"missing matte {matte_path} (run studio/bin/track_subject.py)")
            m = cv2.warpAffine(matte, affine(x0, y0, w, matte.shape[1], matte.shape[0]), (OW, OH), flags=cv2.INTER_LINEAR,
                               borderMode=cv2.BORDER_REPLICATE)
            menc.stdin.write(m.tobytes())
            facepos.append(None if cut else [round((fx - x0) / w * OW, 1), round((fy - y0) / w * OH, 1),
                                             round(fw / w * OW, 1)])
            out_i += 1
        dec.stdout.close()
        dec.wait()
        print(f"  range {idx:2d} {r['beat']:8} {n:4d} frames{' +cutaway' if cuts else ''}  "
              f"({out_i / (time.time() - t0):.1f} fps)", flush=True)
    enc.stdin.close(); menc.stdin.close()
    enc.wait(); menc.wait()
    (EDIT / "facepos.json").write_text(json.dumps({"fps": FPS, "frames": facepos}))
    (EDIT / "animations" / "overlay" / "facepos.js").write_text(
        "window.FACE = " + json.dumps({"fps": FPS, "frames": facepos}) + ";\n")
    print(f"wrote {args.output}, mask.mkv, facepos ({out_i} frames, {out_i / FPS:.2f}s) in {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
