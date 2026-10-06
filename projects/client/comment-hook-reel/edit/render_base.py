"""Base picture: 4K source -> 9:16 crop -> grade -> smooth zoom -> 1080x1920 @ 50 fps.

Zooms are done per frame in float (cv2.warpAffine) from a 1440x2560
intermediate, so slow push-ins have no integer stepping. Each zoom is anchored
on the face, which stays put while the frame tightens around it.

    studio/.venv/bin/python edit/render_base.py [-o edit/base.mp4] [--only BEAT]
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
FPS = TL["fps"]
OW, OH = 1080, 1920
IW, IH = 1440, 2560                       # intermediate, 1.33x headroom over the output
ANCHOR = {"C2412": (0.42, 0.53), "C2416": (0.40, 0.53)}   # face, as a fraction of the 9:16 frame
GRADE = "eq=contrast=1.045:saturation=1.06:gamma=0.985"

# Zoom plan per range (index in timeline.json). Keys: (t, z) with t = local
# seconds, "end", or ("w", src_time[, offset]) = a word's start in that range.
# A framing change on (almost) every cut keeps a pattern interrupt every ~3 s;
# glued cuts (false start, breath inside a phrase) keep the framing.
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


def ease_io(x: float) -> float:
    return 4 * x ** 3 if x < 0.5 else 1 - (-2 * x + 2) ** 3 / 2


def zoom_at(keys: list[list[float]], t: float) -> float:
    if t <= keys[0][0]:
        return keys[0][1]
    for (t0, z0), (t1, z1) in zip(keys, keys[1:]):
        if t <= t1:
            return z0 + (z1 - z0) * ease_io((t - t0) / max(t1 - t0, 1e-6))
    return keys[-1][1]


def decoder(clip: str, start: float, n: int) -> subprocess.Popen:
    vf = (f"crop=2160:3840:0:128,scale={IW}:{IH}:flags=lanczos,{GRADE},format=bgr24")
    return subprocess.Popen(
        ["ffmpeg", "-v", "error", "-ss", f"{start:.3f}", "-i", str(SRC / f"{clip}.MP4"),
         "-frames:v", str(n), "-vf", vf, "-f", "rawvideo", "-pix_fmt", "bgr24", "-"],
        stdout=subprocess.PIPE, bufsize=IW * IH * 3 * 2)


def sharpen(img: np.ndarray) -> np.ndarray:
    blur = cv2.GaussianBlur(img, (0, 0), 1.1)
    return cv2.addWeighted(img, 1.35, blur, -0.35, 0)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("-o", "--output", type=Path, default=EDIT / "base.mp4")
    ap.add_argument("--only", default=None, help="Render a single beat (for checks)")
    ap.add_argument("--crf", type=int, default=12)
    args = ap.parse_args()

    words = TL["words"]

    def local_keys(idx: int, r: dict) -> list[tuple[float, float]]:
        out = []
        for k, z in PLAN[idx]:
            if k == "end":
                t = r["duration"]
            elif isinstance(k, tuple):
                hit = next(x for x in words if abs(x["src"] - k[1]) < 0.03 and x["id"].startswith(r["source"]))
                t = hit["start"] - r["out_start"] + (k[2] if len(k) > 2 else 0)
            else:
                t = k
            out.append((t, z))
        return out

    for i, r in enumerate(TL["ranges"]):
        r["zoom"] = local_keys(i, r)
    ranges = [r for r in TL["ranges"] if not args.only or r["beat"] == args.only]
    enc = subprocess.Popen(
        ["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{OW}x{OH}",
         "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "fast", "-crf", str(args.crf),
         "-pix_fmt", "yuv420p", "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709",
         str(args.output)], stdin=subprocess.PIPE)
    t0 = time.time()
    total = 0
    for r in ranges:
        ax, ay = ANCHOR[r["source"]]
        ax, ay = ax * IW, ay * IH
        dec = decoder(r["source"], r["src_start"], r["frames"])
        for i in range(r["frames"]):
            buf = dec.stdout.read(IW * IH * 3)
            if len(buf) < IW * IH * 3:
                sys.exit(f"{r['beat']}: decoder ended at frame {i}/{r['frames']}")
            frame = np.frombuffer(buf, np.uint8).reshape(IH, IW, 3)
            z = zoom_at(r["zoom"], i / FPS)
            w = IW / z
            s = OW / w
            x0, y0 = ax * (1 - 1 / z), ay * (1 - 1 / z)
            m = np.float32([[s, 0, -x0 * s], [0, s, -y0 * s]])
            out = cv2.warpAffine(frame, m, (OW, OH), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REFLECT)
            enc.stdin.write(sharpen(out).tobytes())
            total += 1
        dec.wait()
        el = time.time() - t0
        print(f"  {r['beat']:8} {r['frames']:4d} frames  ({total / el:.1f} fps)", flush=True)
    enc.stdin.close()
    enc.wait()
    print(f"wrote {args.output} ({total} frames, {total / FPS:.2f}s) in {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
