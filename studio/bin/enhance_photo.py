"""Enhance a photo/screenshot for a cover: Real-ESRGAN x4 upscale + HDR look.

Two stages, because torch and OpenCV live in different venvs:

    studio/.venv-darija/bin/python studio/bin/enhance_photo.py upscale in.png x4.png
    studio/.venv/bin/python        studio/bin/enhance_photo.py hdr x4.png out.png [--width 2160] [--hdr 1.0]

upscale: Real-ESRGAN x4plus (studio/.models/RealESRGAN_x4plus.pth; RRDBNet is
         defined below, so no extra packages), tiled on CPU (torch + Pillow).
hdr:     resize to --width (aspect kept), then the HDR look (--hdr 0..1.5):
         shadows lifted and highlights held on a smooth base layer, local detail
         (clarity) boosted, gentle vibrance that spares skin. 0 = resize only.

Weights: https://github.com/xinntao/Real-ESRGAN/releases/download/v0.1.0/RealESRGAN_x4plus.pth
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

import numpy as np

try:                                   # upscale stage (Darija venv)
    import torch
    from torch import nn
    from torch.nn import functional as F
except ImportError:                    # hdr stage (studio venv)
    torch = None

MODEL = Path(__file__).resolve().parents[1] / ".models" / "RealESRGAN_x4plus.pth"


if torch is not None:
    class RDB(nn.Module):
        def __init__(self, nf: int = 64, gc: int = 32):
            super().__init__()
            self.conv1 = nn.Conv2d(nf, gc, 3, 1, 1)
            self.conv2 = nn.Conv2d(nf + gc, gc, 3, 1, 1)
            self.conv3 = nn.Conv2d(nf + 2 * gc, gc, 3, 1, 1)
            self.conv4 = nn.Conv2d(nf + 3 * gc, gc, 3, 1, 1)
            self.conv5 = nn.Conv2d(nf + 4 * gc, nf, 3, 1, 1)
            self.lrelu = nn.LeakyReLU(0.2, True)

        def forward(self, x):
            x1 = self.lrelu(self.conv1(x))
            x2 = self.lrelu(self.conv2(torch.cat((x, x1), 1)))
            x3 = self.lrelu(self.conv3(torch.cat((x, x1, x2), 1)))
            x4 = self.lrelu(self.conv4(torch.cat((x, x1, x2, x3), 1)))
            return self.conv5(torch.cat((x, x1, x2, x3, x4), 1)) * 0.2 + x


    class RRDB(nn.Module):
        def __init__(self, nf: int, gc: int = 32):
            super().__init__()
            self.rdb1, self.rdb2, self.rdb3 = RDB(nf, gc), RDB(nf, gc), RDB(nf, gc)

        def forward(self, x):
            return self.rdb3(self.rdb2(self.rdb1(x))) * 0.2 + x


    class RRDBNet(nn.Module):
        def __init__(self, nf: int = 64, nb: int = 23, gc: int = 32):
            super().__init__()
            self.conv_first = nn.Conv2d(3, nf, 3, 1, 1)
            self.body = nn.Sequential(*[RRDB(nf, gc) for _ in range(nb)])
            self.conv_body = nn.Conv2d(nf, nf, 3, 1, 1)
            self.conv_up1 = nn.Conv2d(nf, nf, 3, 1, 1)
            self.conv_up2 = nn.Conv2d(nf, nf, 3, 1, 1)
            self.conv_hr = nn.Conv2d(nf, nf, 3, 1, 1)
            self.conv_last = nn.Conv2d(nf, 3, 3, 1, 1)
            self.lrelu = nn.LeakyReLU(0.2, True)

        def forward(self, x):
            feat = self.conv_first(x)
            feat = feat + self.conv_body(self.body(feat))
            feat = self.lrelu(self.conv_up1(F.interpolate(feat, scale_factor=2, mode="nearest")))
            feat = self.lrelu(self.conv_up2(F.interpolate(feat, scale_factor=2, mode="nearest")))
            return self.conv_last(self.lrelu(self.conv_hr(feat)))


def upscale4(rgb8: np.ndarray, tile: int = 192, pad: int = 12) -> np.ndarray:
    net = RRDBNet()
    sd = torch.load(MODEL, map_location="cpu", weights_only=True)
    net.load_state_dict(sd.get("params_ema", sd.get("params", sd)), strict=True)
    net.eval()
    torch.set_num_threads(max(1, torch.get_num_threads()))
    rgb = rgb8.astype(np.float32) / 255.0
    h, w = rgb.shape[:2]
    out = np.zeros((h * 4, w * 4, 3), np.float32)
    x = torch.from_numpy(rgb).permute(2, 0, 1)[None]
    tiles = [(y0, x0) for y0 in range(0, h, tile) for x0 in range(0, w, tile)]
    t0 = time.time()
    with torch.inference_mode():
        for k, (y0, x0) in enumerate(tiles):
            y1, x1 = min(y0 + tile, h), min(x0 + tile, w)
            py0, px0, py1, px1 = max(y0 - pad, 0), max(x0 - pad, 0), min(y1 + pad, h), min(x1 + pad, w)
            sr = net(x[:, :, py0:py1, px0:px1]).clamp_(0, 1)[0].permute(1, 2, 0).numpy()
            oy, ox = (y0 - py0) * 4, (x0 - px0) * 4
            out[y0 * 4:y1 * 4, x0 * 4:x1 * 4] = sr[oy:oy + (y1 - y0) * 4, ox:ox + (x1 - x0) * 4]
            if k % 10 == 0:
                print(f"  tile {k + 1}/{len(tiles)} ({time.time() - t0:.0f}s)", flush=True)
    return (out * 255.0 + 0.5).astype(np.uint8)


def hdr_look(img_bgr: np.ndarray, amount: float = 1.0) -> np.ndarray:
    """Local tone mapping on L (Lab): base/detail split with an edge-aware filter.

    Shadows and dark midtones open up (faces in shade, dark clothes), highlights
    are held, local detail gets moderate clarity, and colours gain vibrance
    except in the skin-hue band, so faces stay natural (no orange cast).
    """
    import cv2
    if amount <= 0:
        return img_bgr
    lab = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2LAB).astype(np.float32)
    L = lab[:, :, 0] / 255.0
    short = min(L.shape)
    base = cv2.bilateralFilter(L, d=0, sigmaColor=0.12, sigmaSpace=short / 60)
    detail = L - base
    lift, hold = 0.26 * amount, 0.10 * amount
    b = base + lift * base * (1 - base) ** 2 * 2.4 - hold * np.clip(base - 0.75, 0, 1) ** 2 * 4
    b = np.clip(b, 0, 1)
    fine = L - cv2.GaussianBlur(L, (0, 0), 1.2)
    Ln = np.clip(b + detail * (1 + 0.45 * amount) + fine * 0.08 * amount, 0, 1)
    lab[:, :, 0] = Ln * 255.0
    out = cv2.cvtColor(lab.astype(np.uint8), cv2.COLOR_LAB2BGR)
    hsv = cv2.cvtColor(out, cv2.COLOR_BGR2HSV).astype(np.float32)
    h, s = hsv[:, :, 0], hsv[:, :, 1] / 255.0
    skin = np.clip(1 - np.abs(h - 13) / 12, 0, 1)            # OpenCV hue 0-180: skin/orange ~ 1-25
    boost = 0.16 * amount * (1 - s) * s * 2.0 * (1 - 0.85 * skin)
    hsv[:, :, 1] = np.clip(s + boost - 0.04 * amount * skin * s, 0, 1) * 255.0
    return cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2BGR)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("stage", choices=["upscale", "hdr"])
    ap.add_argument("input", type=Path)
    ap.add_argument("output", type=Path)
    ap.add_argument("--width", type=int, default=2160, help="hdr: final width (aspect kept)")
    ap.add_argument("--hdr", type=float, default=1.0)
    args = ap.parse_args()
    if args.stage == "upscale":
        from PIL import Image
        rgb = np.asarray(Image.open(args.input).convert("RGB"))
        print(f"{args.input.name}: {rgb.shape[1]}x{rgb.shape[0]}")
        out = upscale4(rgb)
        Image.fromarray(out).save(args.output)
        print(f"wrote {args.output} ({out.shape[1]}x{out.shape[0]}, x4)")
        return
    import cv2
    img = cv2.imread(str(args.input), cv2.IMREAD_COLOR)
    if img is None:
        raise SystemExit(f"cannot read {args.input}")
    tw = args.width
    th = round(img.shape[0] * tw / img.shape[1])
    img = cv2.resize(img, (tw, th), interpolation=cv2.INTER_AREA if tw < img.shape[1] else cv2.INTER_LANCZOS4)
    img = hdr_look(img, args.hdr)
    cv2.imwrite(str(args.output), img)
    print(f"wrote {args.output} ({tw}x{th}, hdr {args.hdr})")


if __name__ == "__main__":
    main()
