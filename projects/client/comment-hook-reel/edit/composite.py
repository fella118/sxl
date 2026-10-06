"""Composite: base + depth layers + mix -> H.264.

Per frame (v3):
  1. base.mp4, with selective grayscale on the background during EV["gray"]
     windows (the speaker stays in colour, through mask.mkv)
  2. back layer (animations/overlay/frames_back): drawn behind the speaker,
     alpha multiplied by (1 - mask)
  3. front layer (animations/overlay/frames_front): drawn over everything

    studio/.venv/bin/python edit/composite.py -o edit/preview_v3.mp4 [--until 21]
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import time
from pathlib import Path

import cv2
import numpy as np

EDIT = Path(__file__).resolve().parent
TL = json.loads((EDIT / "timeline.json").read_text())
EV = json.loads(re.sub(r"^window\.EV = |;\s*$", "", (EDIT / "animations/overlay/events.js").read_text()))
W, H, FPS = TL["width"], TL["height"], TL["fps"]
OVL = EDIT / "animations" / "overlay"
RAMP = 0.15   # grayscale fade in/out, seconds


def gray_weight(t: float) -> float:
    g = 0.0
    for a, b in EV.get("gray", []):
        if a - RAMP <= t <= b + RAMP:
            g = max(g, min(1.0, (t - (a - RAMP)) / RAMP, ((b + RAMP) - t) / RAMP))
    return g


def load_rgba(path: Path):
    if not path.exists():
        return None
    ov = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
    return ov[:, :, :3].astype(np.float32), ov[:, :, 3:4].astype(np.float32) / 255


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("-o", "--output", type=Path, required=True)
    ap.add_argument("--until", type=float, default=None)
    ap.add_argument("--crf", type=int, default=16)
    ap.add_argument("--preset", default="medium")
    args = ap.parse_args()

    n = round((args.until or TL["duration"]) * FPS)
    dec = subprocess.Popen(["ffmpeg", "-nostdin", "-v", "error", "-i", str(EDIT / "base.mp4"), "-f", "rawvideo",
                            "-pix_fmt", "bgr24", "-"], stdout=subprocess.PIPE, bufsize=W * H * 6)
    mdec = subprocess.Popen(["ffmpeg", "-nostdin", "-v", "error", "-i", str(EDIT / "mask.mkv"), "-f", "rawvideo",
                             "-pix_fmt", "gray", "-"], stdout=subprocess.PIPE, bufsize=W * H * 2)
    enc = subprocess.Popen(
        ["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{W}x{H}", "-r", str(FPS),
         "-i", "-", "-i", str(EDIT / "mix.wav"), "-map", "0:v", "-map", "1:a",
         "-c:v", "libx264", "-preset", args.preset, "-crf", str(args.crf), "-profile:v", "high",
         "-pix_fmt", "yuv420p", "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709",
         "-c:a", "aac", "-b:a", "256k", "-ar", "48000", "-movflags", "+faststart", "-shortest",
         str(args.output)], stdin=subprocess.PIPE)
    t0, stats = time.time(), {"back": 0, "front": 0, "gray": 0}
    for i in range(n):
        buf = dec.stdout.read(W * H * 3)
        mbuf = mdec.stdout.read(W * H)
        if len(buf) < W * H * 3 or len(mbuf) < W * H:
            raise SystemExit(f"base/mask ended at frame {i}/{n}")
        base = np.frombuffer(buf, np.uint8).reshape(H, W, 3)
        m = np.frombuffer(mbuf, np.uint8).reshape(H, W, 1).astype(np.float32) / 255
        t = i / FPS
        back, front, g = load_rgba(OVL / "frames_back" / f"{i:06d}.png"), load_rgba(OVL / "frames_front" / f"{i:06d}.png"), gray_weight(t)
        if back is None and front is None and g == 0:
            enc.stdin.write(base.tobytes())
            continue
        out = base.astype(np.float32)
        if g > 0:
            gray = cv2.cvtColor(cv2.cvtColor(base, cv2.COLOR_BGR2GRAY), cv2.COLOR_GRAY2BGR).astype(np.float32) * 0.82
            bg = out * (1 - g) + gray * g
            out = out * m + bg * (1 - m)
            stats["gray"] += 1
        if back is not None:
            rgb, a = back
            a = a * (1 - m)
            out = out * (1 - a) + rgb * a
            stats["back"] += 1
        if front is not None:
            rgb, a = front
            out = out * (1 - a) + rgb * a
            stats["front"] += 1
        enc.stdin.write(np.clip(out + 0.5, 0, 255).astype(np.uint8).tobytes())
    enc.stdin.close()
    enc.wait(); dec.terminate(); mdec.terminate()
    print(f"wrote {args.output}: {n} frames, layers {stats} in {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
