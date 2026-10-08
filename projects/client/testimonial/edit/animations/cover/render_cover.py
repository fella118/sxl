"""cover.html -> deliver/testimonial_cover_v<N>.png/.jpg (1080x1920, headless Chromium).

    studio/.venv/bin/python edit/animations/cover/render_cover.py [N] [page.html] [--scale 2]

bg.png (gitignored) is the founder's listening close-up, a clean frame of the
base render: ffmpeg -ss 46.8 -i edit/base.mp4 -frames:v 1 edit/animations/cover/bg.png
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

sys.path.insert(0, "/home/user/sxl/studio/bin")
from capture_html import chromium  # noqa: E402

HERE = Path(__file__).resolve().parent
DELIVER = HERE.parents[2] / "deliver"


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    n = args[0] if args else "1"
    page_file = args[1] if len(args) > 1 else "cover.html"
    scale = 2 if "--scale" in sys.argv and sys.argv[sys.argv.index("--scale") + 1] == "2" else 1
    DELIVER.mkdir(exist_ok=True)
    png = DELIVER / f"testimonial_cover_v{n}.png"
    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=chromium(), args=["--disable-gpu", "--font-render-hinting=none"])
        page = browser.new_page(viewport={"width": 1080, "height": 1920}, device_scale_factor=scale)
        page.goto((HERE / page_file).as_uri())
        faces = ['400 64px "Anton"', '700 40px "Cairo"']            # loaded explicitly: fonts load lazily
        page.evaluate("""async (faces) => { await Promise.all(faces.map(f => document.fonts.load(f, "AVIS 12 éa")));
                                             await document.fonts.ready; }""", faces)
        page.wait_for_timeout(300)
        ok = page.evaluate("(faces) => faces.every(f => document.fonts.check(f))", faces)
        if not ok:
            sys.exit("fonts not loaded")
        page.screenshot(path=str(png))
        browser.close()
    jpg = png.with_suffix(".jpg")
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(png), "-q:v", "2", str(jpg)], check=True)
    if scale == 2:                                   # Instagram size next to the 4K master
        ig = png.with_name(png.stem + "_1080.jpg")
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(png), "-vf", "scale=1080:1920:flags=lanczos",
                        "-q:v", "2", str(ig)], check=True)
        print(f"wrote {ig}")
    print(f"wrote {png} and {jpg}")


if __name__ == "__main__":
    main()
