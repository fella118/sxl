"""Natural teeth retouch for a cover photo: whiten, clean the stains, fill or soften gaps.

    studio/.venv/bin/python studio/bin/retouch_teeth.py in.png out.png --roi x0,y0,x1,y1
                            [--strength 0.85] [--core-l 172] [--max-chroma 0] [--min-area 250]
                            [--gaps 0] [--row "x,y x,y ..."] [--mask mask.png]

Works in Lab (OpenCV 8-bit: 128 = neutral a*/b*) inside the mouth ROI (a box around
the open mouth, in the image's pixels):
  - clean enamel: bright (L > --core-l, 172 by default; lower it for greyer or
    darker teeth) and not red (a* < 150). Lips (a* ~150-175), gums (a* ~160-177)
    and skin stay out. --max-chroma C also requires near-neutral enamel, for
    grey-white teeth next to light, warm skin;
  - stained / shaded enamel: the mask grows from the clean enamel (at most 24 px)
    into pixels that are bright enough (L > 120) and yellow-orange rather than
    pink ((b*-128) > 1.1 (a*-128)): the brown bands between the lower teeth and
    along the gum line join the mask, gums and lips never do (pink), and the dark
    bite line and mouth corners (L < 120) stop the growth;
  - --gaps W: dark holes between the teeth (L < 110, at least W px thick, inside the
    teeth row) are inpainted with the tooth around them, before the whitening.
    Thinner dark lines stay, so the teeth remain separate; 0 = off. --row draws the
    teeth row by hand (a polygon) when gaps sit next to the dark mouth corners, which
    must stay dark; inside it, dark hairlines between teeth are softened to a shade;
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

L_TARGET, B_TARGET = 234.0, 135.0      # bright, slightly warm white


def masked_blur(x: np.ndarray, m: np.ndarray, sigma: float) -> np.ndarray:
    num = cv2.GaussianBlur(x * m, (0, 0), sigma)
    den = cv2.GaussianBlur(m, (0, 0), sigma)
    return num / np.maximum(den, 1e-4)


def teeth_mask(L: np.ndarray, A: np.ndarray, B: np.ndarray, core_l: float = 172,
               max_chroma: float = 0, min_area: int = 250) -> tuple[np.ndarray, np.ndarray]:
    """(clean enamel, all teeth incl. stained/shaded enamel) as uint8 0/1."""
    core = (L > core_l) & (A < 150)
    if max_chroma > 0:                                     # near-neutral teeth next to light, warm skin
        core &= np.hypot(A - 128, B - 128) < max_chroma
    core = core.astype(np.uint8)
    core = cv2.morphologyEx(core, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    n, lbl, stats, _ = cv2.connectedComponentsWithStats(core, 8)
    keep = np.zeros_like(core)
    for i in range(1, n):
        if stats[i, cv2.CC_STAT_AREA] >= min_area:
            keep[lbl == i] = 1
    core = keep
    cand = ((L > 120) & (A < 157) & ((B - 128) > 1.1 * (A - 128)) | (core > 0)).astype(np.uint8)
    cross = cv2.getStructuringElement(cv2.MORPH_CROSS, (3, 3))
    grown = core.copy()
    for _ in range(24):                                    # geodesic growth through tooth-coloured pixels
        grown = cv2.dilate(grown, cross) & cand
    holes = cv2.morphologyEx(grown, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8)) & (L > 120).astype(np.uint8)
    return core, np.maximum(grown, holes)


def fill_dark_gaps(roi: np.ndarray, teeth: np.ndarray, L: np.ndarray, width: int,
                   row: np.ndarray | None = None) -> tuple[np.ndarray, np.ndarray]:
    """Inpaint dark holes (L < 110, >= width px thick) inside the teeth row. Returns (filled roi, gap mask 0/1).

    row: where holes may be filled (0/1). Default: the teeth mask closed and hole-filled; pass a
    hand-drawn polygon (--row) when gaps sit at the ends of the row, next to the dark mouth corners.
    """
    ell = lambda d: cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (d, d))
    if row is None:
        closed = cv2.morphologyEx(teeth, cv2.MORPH_CLOSE, ell(4 * width + 1))
        cnts, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        row = np.zeros_like(teeth)
        cv2.drawContours(row, cnts, -1, 1, -1)             # the teeth row, holes included
    dark = ((L < 110) & (row > 0) & (teeth == 0)).astype(np.uint8)
    blobs = cv2.morphologyEx(dark, cv2.MORPH_OPEN, ell(width))
    cross = cv2.getStructuringElement(cv2.MORPH_CROSS, (3, 3))
    for _ in range(4 * width):                             # whole blobs, their thin tails included
        blobs = cv2.dilate(blobs, cross) & dark
    gap = cv2.dilate(blobs, ell(5)) & row                  # + the soft edge, never past the row
    return cv2.inpaint(roi, gap * 255, width, cv2.INPAINT_TELEA), gap


def retouch(img: np.ndarray, roi_box: tuple[int, int, int, int], strength: float = 1.0, core_l: float = 172,
            max_chroma: float = 0, gaps: int = 0, row_pts: list[tuple[int, int]] | None = None,
            min_area: int = 250) -> tuple[np.ndarray, np.ndarray]:
    x0, y0, x1, y1 = roi_box
    roi = img[y0:y1, x0:x1]
    row = None
    if row_pts:
        row = np.zeros(roi.shape[:2], np.uint8)
        cv2.fillPoly(row, [np.array([(x - x0, y - y0) for x, y in row_pts], np.int32)], 1)
    near_row = None if row is None else cv2.dilate(row, np.ones((9, 9), np.uint8))

    def masks(L, A, B):
        core, teeth = teeth_mask(L, A, B, core_l, max_chroma, min_area)
        if near_row is not None:                           # a drawn row also bounds the teeth: no skin leaks
            core, teeth = core & near_row, teeth & near_row
        return core, teeth

    lab = cv2.cvtColor(roi, cv2.COLOR_BGR2LAB).astype(np.float32)
    L, A, B = lab[:, :, 0], lab[:, :, 1], lab[:, :, 2]
    core, teeth = masks(L, A, B)
    gap = np.zeros_like(teeth)
    if gaps > 0:
        filled, gap = fill_dark_gaps(roi, teeth, L, gaps, row)
        lab = cv2.cvtColor(filled, cv2.COLOR_BGR2LAB).astype(np.float32)
        L, A, B = lab[:, :, 0], lab[:, :, 1], lab[:, :, 2]
        core, teeth = masks(L, A, B)

    # small gaps: inside the teeth area (closing), mid-dark pixels darker than their neighbourhood
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (13, 13))
    area = cv2.morphologyEx(teeth, cv2.MORPH_CLOSE, k)
    Lc = cv2.morphologyEx(L, cv2.MORPH_CLOSE, k)
    small = (area > 0) & (teeth == 0) & (L > 100) & (Lc - L > 18)
    inside = area > 0
    if row is not None:                                    # inside a drawn row, dark hairlines become soft shades too
        small |= (row > 0) & (teeth == 0) & (Lc - L > 18)
        inside |= row > 0
    gap_w = cv2.GaussianBlur(small.astype(np.float32), (0, 0), 1.5) * inside
    fill = np.clip(gap_w * 0.7 * strength, 0, 1)
    Ac = cv2.morphologyEx(A, cv2.MORPH_CLOSE, k)
    Bc = cv2.morphologyEx(B, cv2.MORPH_CLOSE, k)
    L = L + (Lc - L) * fill
    A = A + (np.minimum(Ac, A) - A) * fill
    B = B + (Bc - B) * fill

    sel = np.maximum(np.maximum(teeth, gap).astype(np.float32), (fill > 0.05).astype(np.float32))
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
          f"(clean {int(core.sum())}), stain px {int((stain > 0.5).sum())}, gaps filled {int(gap.sum())} px")
    return res, full_mask


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("input", type=Path)
    ap.add_argument("output", type=Path)
    ap.add_argument("--roi", required=True, help="x0,y0,x1,y1: a box around the open mouth")
    ap.add_argument("--strength", type=float, default=0.85, help="0..1: 0.85 = clean, natural white")
    ap.add_argument("--core-l", type=float, default=172, help="L threshold for clean enamel (lower for grey teeth)")
    ap.add_argument("--max-chroma", type=float, default=0,
                    help="Clean enamel must be this close to neutral (0 = off; ~14 when the skin is light)")
    ap.add_argument("--gaps", type=int, default=0, help="Inpaint dark holes at least this many px thick (0 = off)")
    ap.add_argument("--row", default=None, help='"x,y x,y ...": polygon of the teeth row where gaps may be filled')
    ap.add_argument("--min-area", type=int, default=250, help="Smallest clean-enamel piece kept (px)")
    ap.add_argument("--mask", type=Path, default=None, help="Also write the teeth mask (QC)")
    args = ap.parse_args()
    img = cv2.imread(str(args.input), cv2.IMREAD_COLOR)
    if img is None:
        raise SystemExit(f"cannot read {args.input}")
    box = tuple(int(v) for v in args.roi.split(","))
    row = [tuple(int(v) for v in p.split(",")) for p in args.row.split()] if args.row else None
    res, m = retouch(img, box, args.strength, args.core_l, args.max_chroma, args.gaps, row, args.min_area)
    cv2.imwrite(str(args.output), res)
    if args.mask:
        cv2.imwrite(str(args.mask), (m * 255).astype(np.uint8))
    print(f"wrote {args.output}")


if __name__ == "__main__":
    main()
