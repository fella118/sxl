"""Capture an HTML motion-graphics composition to transparent PNG frames.

The page must define:
    window.ready       a Promise that resolves once fonts/images are loaded (reject on failure)
    window.seek(t)     put every element in its state at time t (seconds), deterministically
    window.anyVisible  optional; frames where it returns false are skipped (no file)

Frames are written as <out>/NNNNNN.png (frame index at --fps). Missing files
mean "nothing on screen" to the compositor.

Usage:
    python studio/bin/capture_html.py page.html out_dir --duration 47.72 --fps 50 --workers 3
    python studio/bin/capture_html.py page.html stills --times 1.2,9.8,24 --background "#333"
"""

from __future__ import annotations

import argparse
import glob
import multiprocessing as mp
import time
from pathlib import Path

CHROMIUM_CANDIDATES = [
    "/opt/pw-browsers/chromium-*/chrome-linux/chrome",
    "/opt/pw-browsers/chromium_headless_shell-*/chrome-linux/headless_shell",
]


def chromium() -> str | None:
    for pattern in CHROMIUM_CANDIDATES:
        hits = sorted(glob.glob(pattern))
        if hits:
            return hits[-1]
    return None


def open_page(pw, html: Path, width: int, height: int, query: str = ""):
    browser = pw.chromium.launch(executable_path=chromium(), args=["--disable-gpu", "--font-render-hinting=none"])
    page = browser.new_page(viewport={"width": width, "height": height}, device_scale_factor=1)
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(html.resolve().as_uri() + (f"?{query}" if query else ""))
    page.wait_for_function("window.ready !== undefined")
    page.evaluate("window.ready")
    if errors:
        raise RuntimeError("page errors: " + "; ".join(errors))
    return browser, page


def worker(args) -> int:
    html, out, frames, fps, width, height, background, query = args
    from playwright.sync_api import sync_playwright

    n = 0
    with sync_playwright() as pw:
        browser, page = open_page(pw, Path(html), width, height, query)
        if background:
            page.evaluate(f"document.body.style.background = {background!r}")
        has_vis = page.evaluate("typeof window.anyVisible === 'function'")
        for f in frames:
            page.evaluate(f"window.seek({f / fps})")
            if has_vis and not background and not page.evaluate("window.anyVisible()"):
                continue
            page.screenshot(path=str(Path(out) / f"{f:06d}.png"), omit_background=not background)
            n += 1
        browser.close()
    return n


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("html", type=Path)
    ap.add_argument("out", type=Path)
    ap.add_argument("--duration", type=float, help="Seconds to capture (all frames)")
    ap.add_argument("--times", default=None, help="Comma-separated times for stills instead")
    ap.add_argument("--fps", type=float, default=50)
    ap.add_argument("--width", type=int, default=1080)
    ap.add_argument("--height", type=int, default=1920)
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--background", default=None, help="Opaque background for previews, e.g. #333")
    ap.add_argument("--query", default="", help="URL query for the page, e.g. layer=back")
    ap.add_argument("--start", type=float, default=0.0, help="First second to capture (with --duration)")
    args = ap.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)
    if args.times:
        frames = [round(float(t) * args.fps) for t in args.times.split(",")]
    else:
        frames = list(range(round(args.start * args.fps), round(args.duration * args.fps)))
    chunks = [frames[i::args.workers] for i in range(args.workers)]
    t0 = time.time()
    jobs = [(str(args.html), str(args.out), c, args.fps, args.width, args.height, args.background, args.query)
            for c in chunks if c]
    with mp.get_context("spawn").Pool(len(jobs)) as pool:
        written = sum(pool.map(worker, jobs))
    print(f"{written}/{len(frames)} frames written to {args.out} in {time.time() - t0:.1f}s")


if __name__ == "__main__":
    main()
