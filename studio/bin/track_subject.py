"""Track the speaker for a project's cut: face position + person matte per source frame.

For every source frame inside the cut's ranges (plus a margin for smoothing):
  - YuNet (OpenCV zoo, MIT) face box and eye landmarks, normalized to the 9:16 frame
  - MODNet (Apache-2.0) portrait matte, 416x736 uint8

Writes <edit>/track/<clip>.faces.json  {frame: [cx, cy, w, h, score]}  (cx/cy = eye midpoint)
       <edit>/track/<clip>/<frame:06d>.png   matte

    studio/.venv/bin/python studio/bin/track_subject.py projects/<c>/<p>/edit [--margin 12]
"""

from __future__ import annotations

import argparse
import json
import subprocess
import time
from pathlib import Path

import cv2
import numpy as np
import onnxruntime as ort

MODELS = Path(__file__).resolve().parent.parent / ".models"
AW, AH = 540, 960          # analysis frame (9:16)
MW, MH = 416, 736          # matte size (multiple of 32)
CROP = "crop=2160:3840:0:128"   # same 9:16 crop as render_base


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("edit", type=Path)
    ap.add_argument("--margin", type=int, default=12, help="Extra frames each side of a range")
    ap.add_argument("--threads", type=int, default=4)
    args = ap.parse_args()

    args.edit = args.edit.resolve()
    tl = json.loads((args.edit / "timeline.json").read_text())
    fps = tl["fps"]
    src_dir = args.edit.parent / "source"
    out_dir = args.edit / "track"
    out_dir.mkdir(exist_ok=True)

    wanted: dict[str, set[int]] = {}
    for r in tl["ranges"]:
        if r.get("src_start") is None:          # pad ranges (held frame under a full-screen card)
            continue
        f0, f1 = round(r["src_start"] * fps), round(r["src_end"] * fps)
        wanted.setdefault(r["source"], set()).update(range(max(0, f0 - args.margin), f1 + args.margin))

    det = cv2.FaceDetectorYN.create(str(MODELS / "yunet.onnx"), "", (AW, AH), 0.6, 0.3, 5)
    so = ort.SessionOptions()
    so.intra_op_num_threads = args.threads
    matting = ort.InferenceSession(str(MODELS / "modnet.onnx"), so, providers=["CPUExecutionProvider"])

    t0, done = time.time(), 0
    for clip, frames in wanted.items():
        faces_path = out_dir / f"{clip}.faces.json"
        faces = json.loads(faces_path.read_text()) if faces_path.exists() else {}
        (out_dir / clip).mkdir(exist_ok=True)
        todo = sorted(f for f in frames if not (out_dir / clip / f"{f:06d}.png").exists() or str(f) not in faces)
        # contiguous runs -> one decoder each
        runs, start = [], None
        for a, b in zip([None] + todo, todo + [None]):
            if a is not None and (b is None or b != a + 1):
                runs.append((start, a))          # close the run ending at a
            if b is not None and (a is None or b != a + 1):
                start = b                        # open a run starting at b
        for f0, f1 in runs:
            n = f1 - f0 + 1
            dec = subprocess.Popen(["ffmpeg", "-nostdin", "-v", "error", "-ss", f"{f0 / fps:.3f}", "-i", str(src_dir / f"{clip}.MP4"),
                                    "-frames:v", str(n), "-vf", f"{CROP},scale={AW}:{AH}:flags=area",
                                    "-f", "rawvideo", "-pix_fmt", "bgr24", "-"], stdout=subprocess.PIPE, stdin=subprocess.DEVNULL)
            for i in range(n):
                buf = dec.stdout.read(AW * AH * 3)
                if len(buf) < AW * AH * 3:
                    break
                img = np.frombuffer(buf, np.uint8).reshape(AH, AW, 3)
                f = f0 + i
                _, found = det.detect(img)
                if found is not None and len(found):
                    best = max(found, key=lambda d: d[2] * d[3] * d[14])
                    x, y, w, h = best[:4]
                    ex, ey = (best[4] + best[6]) / 2, (best[5] + best[7]) / 2
                    faces[str(f)] = [round(float(ex) / AW, 4), round(float(ey) / AH, 4),
                                     round(float(w) / AW, 4), round(float(h) / AH, 4), round(float(best[14]), 3)]
                x = cv2.resize(img, (MW, MH), interpolation=cv2.INTER_AREA)[:, :, ::-1].astype(np.float32) / 255
                x = ((x - 0.5) / 0.5).transpose(2, 0, 1)[None]
                matte = matting.run(None, {"input": x})[0][0, 0]
                cv2.imwrite(str(out_dir / clip / f"{f:06d}.png"), (matte * 255).astype(np.uint8))
                done += 1
                if done % 200 == 0:
                    print(f"  {done} frames ({done / (time.time() - t0):.1f} fps)", flush=True)
            dec.wait()
        faces_path.write_text(json.dumps(faces))
        missing = len([f for f in frames if str(f) not in faces])
        print(f"{clip}: {len(frames)} frames, faces missing on {missing}", flush=True)
    print(f"done in {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
