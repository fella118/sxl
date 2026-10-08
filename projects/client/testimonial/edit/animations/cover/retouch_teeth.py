"""Natural teeth retouch for the cover photo: whiten, clean the stains, soften small gaps.

    studio/.venv/bin/python edit/animations/cover/retouch_teeth.py host4k.png host4k_teeth.png [--strength 0.85]

Works in Lab (OpenCV 8-bit: 128 = neutral a*/b*) inside a mouth ROI (4K cover coordinates):
  - clean enamel: bright (L > 172) and not red (a* < 150). Lips (a* ~175), gums
    (a* ~160-177) and skin (L ~133) stay out;
  - stained / shaded enamel: the mask grows from the clean enamel (at most 24 px)
    into pixels that are bright enough (L > 120) and yellow-orange rather than
    pink ((b*-128) > 1.1 (a*-128)): the brown bands between the lower teeth and
    along the gum line join the mask, gums and lips never do (pink), and the dark
    bite line and mouth corners (L < 120) stop the growth;
  - small mid-dark gaps between teeth (narrower than ~13 px) are lifted toward
    their surroundings; the bite line and mouth corners (L < 100) keep their shadow;
  - stains: their extra darkness is lifted 65% toward the surrounding tooth and
    their yellow is compressed with a soft knee, so a faint warm shade stays
    between the teeth;
  - whitening: a capped low-frequency lift toward L 234 (highlights spared) and
    b* toward a slightly warm white; fine texture stays, so the teeth look real.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import cv2
import numpy as np

ROI = (880, 1855, 1290, 2010)          # x0, y0, x1, y1 around the open mouth (host4k.png, 2160x3840)
L_TARGET, B_TARGET = 234.0, 135.0      # bright, slightly warm white


def masked_blur(x: np.ndarray, m: np.ndarray, sigma: float) -> np.ndarray:
    num = cv2.GaussianBlur(x * m, (0, 0), sigma)
    den = cv2.GaussianBlur(m, (0, 0), sigma)
    return num / np.maximum(den, 1e-4)


def teeth_mask(L: np.ndarray, A: np.ndarray, B: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """(clean enamel, all teeth incl. stained/shaded enamel) as uint8 0/1."""
    core = ((L > 172) & (A < 150)).astype(np.uint8)
    core = cv2.morphologyEx(core, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    n, lbl, stats, _ = cv2.connectedComponentsWithStats(core, 8)
    keep = np.zeros_like(core)
    for i in range(1, n):
        if stats[i, cv2.CC_STAT_AREA] >= 250:
            keep[lbl == i] = 1
    core = keep
    cand = ((L > 120) & (A < 157) & ((B - 128) > 1.1 * (A - 128)) | (core > 0)).astype(np.uint8)
    cross = cv2.getStructuringElement(cv2.MORPH_CROSS, (3, 3))
    grown = core.copy()
    for _ in range(24):                                    # geodesic growth through tooth-coloured pixels
        grown = cv2.dilate(grown, cross) & cand
    holes = cv2.morphologyEx(grown, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8)) & (L > 120).astype(np.uint8)
    return core, np.maximum(grown, holes)


def retouch(img: np.ndarray, strength: float = 1.0) -> tuple[np.ndarray, np.ndarray]:
    x0, y0, x1, y1 = ROI
    roi = img[y0:y1, x0:x1]
    lab = cv2.cvtColor(roi, cv2.COLOR_BGR2LAB).astype(np.float32)
    L, A, B = lab[:, :, 0], lab[:, :, 1], lab[:, :, 2]
    core, teeth = teeth_mask(L, A, B)

    # small gaps: inside the teeth area (closing), mid-dark pixels darker than their neighbourhood
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (13, 13))
    area = cv2.morphologyEx(teeth, cv2.MORPH_CLOSE, k)
    Lc = cv2.morphologyEx(L, cv2.MORPH_CLOSE, k)
    gaps = (area > 0) & (teeth == 0) & (L > 100) & (Lc - L > 18)
    gap_w = cv2.GaussianBlur(gaps.astype(np.float32), (0, 0), 1.5) * (area > 0)
    fill = np.clip(gap_w * 0.7 * strength, 0, 1)
    Ac = cv2.morphologyEx(A, cv2.MORPH_CLOSE, k)
    Bc = cv2.morphologyEx(B, cv2.MORPH_CLOSE, k)
    L = L + (Lc - L) * fill
    A = A + (np.minimum(Ac, A) - A) * fill
    B = B + (Bc - B) * fill

    sel = np.maximum(teeth.astype(np.float32), (fill > 0.05).astype(np.float32))
    m = np.clip(cv2.GaussianBlur(sel, (0, 0), 1.6), 0, 1)
    sel = (m > 0.02).astype(np.float32)
    on = core > 0
    L_ref, B_ref = float(np.median(L[on])), float(np.median(B[on]))

    # stains: yellow above the clean enamel; lift their extra darkness, keep 35% as a soft shade
    L_s, B_s = masked_blur(L, sel, 2.5), masked_blur(B, sel, 2.5)
    L_big = masked_blur(L, sel, 12)
    stain = np.clip((B_s - B_ref - 4) / 14, 0, 1)
    L1 = L + stain * np.clip(L_big - L_s, 0, 60) * 0.65 * strength

    # whiten: capped low-frequency lift toward L_TARGET, highlights spared
    lift = np.clip((L_TARGET - L_big) * 0.5, 0, 16) * strength
    Lw = np.clip(L1 + lift * np.clip((252 - L1) / 30, 0, 1), 0, 250)
    dev = B - B_ref
    dev_c = np.where(dev < 0, dev * 0.6, 0.6 * dev / (1 + np.maximum(dev, 0) / 14))   # soft knee on yellow
    Bw = B + (B_TARGET + dev_c - B) * strength
    Aw = 128 + (A - 128) * (1 - 0.45 * strength)

    new = cv2.cvtColor(np.clip(np.dstack([Lw, Aw, Bw]) + 0.5, 0, 255).astype(np.uint8), cv2.COLOR_LAB2BGR)
    mm = m[:, :, None]                                     # blend in BGR: pixels outside the mask stay bit-exact
    res = img.copy()
    res[y0:y1, x0:x1] = np.clip(roi * (1 - mm) + new.astype(np.float32) * mm + 0.5, 0, 255).astype(np.uint8)
    full_mask = np.zeros(img.shape[:2], np.float32)
    full_mask[y0:y1, x0:x1] = m
    print(f"enamel ref L {L_ref:.0f} b* {B_ref - 128:+.0f}; teeth {int(teeth.sum())} px "
          f"(clean {int(core.sum())}), stain px {int((stain > 0.5).sum())}")
    return res, full_mask


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("input", type=Path)
    ap.add_argument("output", type=Path)
    ap.add_argument("--strength", type=float, default=0.85, help="0..1: 0.85 = clean, natural white")
    ap.add_argument("--mask", type=Path, default=None, help="Also write the teeth mask (QC)")
    args = ap.parse_args()
    img = cv2.imread(str(args.input), cv2.IMREAD_COLOR)
    res, m = retouch(img, args.strength)
    cv2.imwrite(str(args.output), res)
    if args.mask:
        cv2.imwrite(str(args.mask), (m * 255).astype(np.uint8))
    print(f"wrote {args.output}")


if __name__ == "__main__":
    main()
