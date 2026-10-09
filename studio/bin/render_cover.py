"""Render an HTML cover page (1080x1920 CSS px) to PNG + JPG with headless Chromium.

    studio/.venv/bin/python studio/bin/render_cover.py <page.html> <out_stem> [--scale 2]

Writes <out_stem>.png and <out_stem>.jpg. With --scale 2 the page renders at
2160x3840 (device scale factor 2) and <out_stem>_1080.jpg is added for upload.
Every @font-face the page declares is loaded before the screenshot (fonts load
lazily, so a face used only once can otherwise be missing).
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent))
from capture_html import chromium  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("page", type=Path)
    ap.add_argument("out_stem", type=Path, help="e.g. projects/c/p/deliver/p_cover_v1")
    ap.add_argument("--scale", type=int, default=1, choices=[1, 2])
    args = ap.parse_args()
    png = args.out_stem.with_name(args.out_stem.name + ".png")
    png.parent.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=chromium(), args=["--disable-gpu", "--font-render-hinting=none"])
        page = browser.new_page(viewport={"width": 1080, "height": 1920}, device_scale_factor=args.scale)
        page.goto(args.page.resolve().as_uri())
        page.evaluate("""async () => { await Promise.all([...document.fonts].map(f => f.load()));
                                       await document.fonts.ready;
                                       await Promise.all([...document.images].map(i => i.decode())); }""")
        page.wait_for_timeout(300)
        bad = page.evaluate("[...document.fonts].filter(f => f.status !== 'loaded').map(f => f.family)")
        if bad:
            sys.exit(f"fonts not loaded: {bad}")
        page.screenshot(path=str(png))
        browser.close()
    jpg = png.with_suffix(".jpg")
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(png), "-q:v", "2", str(jpg)], check=True)
    print(f"wrote {png} and {jpg}")
    if args.scale == 2:
        ig = png.with_name(png.stem + "_1080.jpg")
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(png), "-vf", "scale=1080:1920:flags=lanczos",
                        "-q:v", "2", str(ig)], check=True)
        print(f"wrote {ig}")


if __name__ == "__main__":
    main()
