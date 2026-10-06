"""Composite: base.mp4 + overlay PNG frames + mix.wav -> final H.264 file.

Overlay frames are animations/overlay/frames/NNNNNN.png (RGBA, straight alpha);
a missing frame means nothing is on screen.

    studio/.venv/bin/python edit/composite.py -o edit/preview_v1.mp4
"""

from __future__ import annotations

import argparse
import json
import subprocess
import time
from pathlib import Path

import cv2
import numpy as np

EDIT = Path(__file__).resolve().parent
TL = json.loads((EDIT / "timeline.json").read_text())
W, H, FPS = TL["width"], TL["height"], TL["fps"]
FRAMES = EDIT / "animations" / "overlay" / "frames"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("-o", "--output", type=Path, required=True)
    ap.add_argument("--crf", type=int, default=16)
    ap.add_argument("--preset", default="medium")
    args = ap.parse_args()

    n = round(TL["duration"] * FPS)
    dec = subprocess.Popen(["ffmpeg", "-v", "error", "-i", str(EDIT / "base.mp4"), "-f", "rawvideo",
                            "-pix_fmt", "bgr24", "-"], stdout=subprocess.PIPE, bufsize=W * H * 6)
    enc = subprocess.Popen(
        ["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{W}x{H}", "-r", str(FPS),
         "-i", "-", "-i", str(EDIT / "mix.wav"), "-map", "0:v", "-map", "1:a",
         "-c:v", "libx264", "-preset", args.preset, "-crf", str(args.crf), "-profile:v", "high",
         "-pix_fmt", "yuv420p", "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709",
         "-c:a", "aac", "-b:a", "256k", "-ar", "48000", "-movflags", "+faststart", "-shortest",
         str(args.output)], stdin=subprocess.PIPE)
    t0, overlaid = time.time(), 0
    for i in range(n):
        buf = dec.stdout.read(W * H * 3)
        if len(buf) < W * H * 3:
            raise SystemExit(f"base.mp4 ended at frame {i}/{n}")
        frame = np.frombuffer(buf, np.uint8).reshape(H, W, 3)
        png = FRAMES / f"{i:06d}.png"
        if png.exists():
            ov = cv2.imread(str(png), cv2.IMREAD_UNCHANGED)
            a = ov[:, :, 3:4].astype(np.uint16)
            frame = ((frame.astype(np.uint16) * (255 - a) + ov[:, :, :3].astype(np.uint16) * a + 127) // 255).astype(np.uint8)
            overlaid += 1
        enc.stdin.write(frame.tobytes())
    enc.stdin.close()
    enc.wait()
    dec.wait()
    print(f"wrote {args.output}: {n} frames ({overlaid} with graphics) in {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
