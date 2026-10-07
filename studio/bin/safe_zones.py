"""Head safe zones per output frame, and a check that graphics never cover the head.

zones:  reads <edit>/mask.mkv + <edit>/facepos.json (from render_base) and adds,
        per frame, the top of the head (from the matte, above the face) and the
        chin (eyes + 0.85 face widths). Rewrites facepos.json and the overlay's
        facepos.js as [eye_x, eye_y, face_w, head_top, chin] (output pixels).

check:  scans a rendered overlay layer (PNG frames) against the head region
        (matte pixels between head_top and chin, around the face) and lists
        frames where graphics cover the head.

    studio/.venv/bin/python studio/bin/safe_zones.py zones <edit> [--js <overlay>/facepos.js]
    studio/.venv/bin/python studio/bin/safe_zones.py check <edit> <frames_dir> [--max-pct 0.5]
"""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

import numpy as np

W, H = 1080, 1920


def masks(edit: Path, n: int):
    dec = subprocess.Popen(["ffmpeg", "-nostdin", "-v", "error", "-i", str(edit / "mask.mkv"), "-f", "rawvideo",
                            "-pix_fmt", "gray", "-"], stdout=subprocess.PIPE, stdin=subprocess.DEVNULL)
    for _ in range(n):
        buf = dec.stdout.read(W * H)
        if len(buf) < W * H:
            break
        yield np.frombuffer(buf, np.uint8).reshape(H, W)
    dec.terminate()


def head_box(m: np.ndarray, f: list) -> tuple[int, int, int, int]:
    """(x0, x1, head_top, chin) for one frame."""
    ex, ey, fw = f[0], f[1], f[2]
    x0, x1 = int(max(0, ex - 0.62 * fw)), int(min(W, ex + 0.62 * fw))
    cols = m[:int(ey), x0:x1] > 128
    rows = np.flatnonzero(cols.mean(axis=1) > 0.12)
    top = int(rows[0]) if len(rows) else int(ey - 0.9 * fw)
    chin = int(min(H, ey + 0.85 * fw))
    return x0, x1, top, chin


def zones(edit: Path, js: Path | None = None) -> None:
    fp = json.loads((edit / "facepos.json").read_text())
    frames = fp["frames"]
    out = []
    for f, m in zip(frames, masks(edit, len(frames))):
        if f is None:
            out.append(None)
            continue
        _, _, top, chin = head_box(m, f)
        out.append([f[0], f[1], f[2], top, chin])
    fp["frames"] = out
    (edit / "facepos.json").write_text(json.dumps(fp))
    js = js or edit / "animations" / "overlay" / "facepos.js"
    js.write_text("window.FACE = " + json.dumps(fp) + ";\n")
    tops = [f[3] for f in out if f]
    chins = [f[4] for f in out if f]
    print(f"{len(out)} frames: head top {min(tops)}..{max(tops)} px, chin {min(chins)}..{max(chins)} px")


def check(edit: Path, frames_dir: Path, max_pct: float) -> None:
    import cv2

    fp = json.loads((edit / "facepos.json").read_text())["frames"]
    bad = []
    for i, m in enumerate(masks(edit, len(fp))):
        png = frames_dir / f"{i:06d}.png"
        if not png.exists() or fp[i] is None:
            continue
        a = cv2.imread(str(png), cv2.IMREAD_UNCHANGED)[:, :, 3]
        x0, x1, top, chin = head_box(m, fp[i])
        head = m[top:chin, x0:x1] > 128
        cover = (a[top:chin, x0:x1] > 96) & head
        pct = 100 * cover.sum() / max(1, head.sum())
        if pct > max_pct:
            bad.append((i, round(i / 50, 2), round(float(pct), 1)))
    print(f"{len(bad)} frames cover more than {max_pct}% of the head")
    runs = []                                   # contiguous stretches, worst coverage in each
    for b in bad:
        if runs and b[0] == runs[-1][1] + 1:
            runs[-1] = (runs[-1][0], b[0], max(runs[-1][2], b[2]))
        else:
            runs.append((b[0], b[0], b[2]))
    for a, z, worst in runs:
        print(f"  {a / 50:6.2f}-{z / 50:6.2f}s  ({z - a + 1} frames, worst {worst}%)")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("mode", choices=["zones", "check"])
    ap.add_argument("edit", type=Path)
    ap.add_argument("frames", type=Path, nargs="?")
    ap.add_argument("--max-pct", type=float, default=0.5)
    ap.add_argument("--js", type=Path, default=None, help="zones: where to write the overlay's facepos.js")
    args = ap.parse_args()
    if args.mode == "zones":
        zones(args.edit.resolve(), args.js.resolve() if args.js else None)
    else:
        check(args.edit.resolve(), args.frames.resolve(), args.max_pct)


if __name__ == "__main__":
    main()
