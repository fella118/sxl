"""cover.html -> deliver/testimonial_cover_v<N>.png/.jpg (1080x1920, headless Chromium).

    studio/.venv/bin/python edit/animations/cover/render_cover.py [N]

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
    n = sys.argv[1] if len(sys.argv) > 1 else "1"
    DELIVER.mkdir(exist_ok=True)
    png = DELIVER / f"testimonial_cover_v{n}.png"
    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=chromium(), args=["--disable-gpu", "--font-render-hinting=none"])
        page = browser.new_page(viewport={"width": 1080, "height": 1920}, device_scale_factor=1)
        page.goto((HERE / "cover.html").as_uri())
        page.evaluate("document.fonts.ready")
        page.wait_for_timeout(300)
        ok = page.evaluate("""() => ['400 64px "Anton"', '700 40px "Cairo"'].every(f => document.fonts.check(f))""")
        if not ok:
            sys.exit("fonts not loaded")
        page.screenshot(path=str(png))
        browser.close()
    jpg = png.with_suffix(".jpg")
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(png), "-q:v", "2", str(jpg)], check=True)
    print(f"wrote {png} and {jpg}")


if __name__ == "__main__":
    main()
