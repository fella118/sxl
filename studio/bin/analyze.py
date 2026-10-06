"""Understand footage before editing: metadata, scenes, frames, audio levels.

For each source writes:
    <edit>/analysis/<stem>/contact.jpg    labelled grid, one frame per scene
    <edit>/analysis/<stem>/scene_NNN.jpg  mid-scene stills (for close looks)
and one combined report at <edit>/analysis.md.

Read contact.jpg first (one image covers the whole clip), then open single
scene stills only where a decision needs them.

Usage:
    python studio/bin/analyze.py <project_dir | video> [...]
    python studio/bin/analyze.py projects/acme/launch --threshold 22 --max-frames 36
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent))
from studio_paths import VIDEO_EXTS, edit_dir_for, find_sources  # noqa: E402


def tc(seconds: float) -> str:
    m, s = divmod(max(seconds, 0.0), 60)
    return f"{int(m):02d}:{s:05.2f}"


def probe(path: Path) -> dict:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)],
        capture_output=True, text=True, check=True,
    )
    return json.loads(out.stdout)


def summarize_probe(info: dict) -> dict:
    fmt = info.get("format", {})
    v = next((s for s in info["streams"] if s["codec_type"] == "video"), None)
    audio = [s for s in info["streams"] if s["codec_type"] == "audio"]
    summary = {
        "duration": float(fmt.get("duration", 0) or 0),
        "size_mb": int(fmt.get("size", 0) or 0) / 1e6,
        "bitrate_kbps": int(fmt.get("bit_rate", 0) or 0) // 1000,
        "audio_tracks": [f"{a.get('codec_name')} {a.get('channels')}ch {a.get('sample_rate')}Hz" for a in audio],
    }
    if v:
        w, h = int(v["width"]), int(v["height"])
        rotation = 0
        for sd in v.get("side_data_list", []):
            if "rotation" in sd:
                rotation = int(sd["rotation"])
        rotation = int(v.get("tags", {}).get("rotate", rotation))
        if abs(rotation) in (90, 270):
            w, h = h, w
        num, den = (v.get("avg_frame_rate") or "0/1").split("/")
        fps = float(num) / float(den) if float(den) else 0.0
        summary.update({
            "width": w, "height": h, "fps": round(fps, 3), "codec": v.get("codec_name"),
            "pix_fmt": v.get("pix_fmt"), "rotation": rotation,
            "orientation": "vertical" if h > w else "horizontal" if w > h else "square",
            "hdr": v.get("color_transfer") in ("smpte2084", "arib-std-b67"),
        })
    return summary


def detect_scenes(path: Path, threshold: float, duration: float) -> list[tuple[float, float]]:
    from scenedetect import ContentDetector, detect

    scenes = detect(str(path), ContentDetector(threshold=threshold, min_scene_len=12))
    spans = [(a.seconds, b.seconds) for a, b in scenes]
    return spans or [(0.0, duration)]


def audio_stats(path: Path) -> dict:
    """Integrated loudness, true peak and silences (ffmpeg ebur128 + silencedetect)."""
    out = subprocess.run(
        ["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-map", "0:a:0?", "-vn",
         "-af", "ebur128=peak=true,silencedetect=noise=-35dB:d=0.6", "-f", "null", "-"],
        capture_output=True, text=True,
    ).stderr
    stats: dict = {"silences": []}
    summary = out[out.rfind("Summary:"):] if "Summary:" in out else ""
    if m := re.search(r"I:\s+(-?[\d.]+) LUFS", summary):
        stats["lufs"] = float(m.group(1))
    if m := re.search(r"LRA:\s+(-?[\d.]+) LU", summary):
        stats["lra"] = float(m.group(1))
    if m := re.search(r"Peak:\s+(-?[\d.]+|-inf) dBFS", summary):
        stats["true_peak"] = m.group(1)
    starts = [float(x) for x in re.findall(r"silence_start: (-?[\d.]+)", out)]
    ends = [(float(e), float(d)) for e, d in re.findall(r"silence_end: ([\d.]+) \| silence_duration: ([\d.]+)", out)]
    stats["silences"] = [(max(s, 0.0), e) for s, (e, _) in zip(starts, ends)]
    return stats


def grab_frame(path: Path, t: float, dest: Path, width: int) -> bool:
    r = subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-ss", f"{t:.3f}", "-i", str(path), "-frames:v", "1",
         "-vf", f"scale={width}:-2", "-q:v", "3", str(dest)],
        capture_output=True,
    )
    return r.returncode == 0 and dest.exists()


def contact_sheet(frames: list[tuple[Path, str]], dest: Path, cols: int) -> None:
    thumbs = [Image.open(p).convert("RGB") for p, _ in frames]
    tw = max(t.width for t in thumbs)
    th = max(t.height for t in thumbs)
    label_h = 22
    rows = (len(thumbs) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * tw, rows * (th + label_h)), (18, 18, 18))
    draw = ImageDraw.Draw(sheet)
    try:
        font = ImageFont.truetype("DejaVuSans-Bold.ttf", 15)
    except OSError:
        font = ImageFont.load_default()
    for i, (img, (_, label)) in enumerate(zip(thumbs, frames)):
        x, y = (i % cols) * tw, (i // cols) * (th + label_h)
        sheet.paste(img, (x, y + label_h))
        draw.text((x + 6, y + 3), label, fill=(255, 220, 90), font=font)
    sheet.save(dest, quality=85)


def analyze(video: Path, args) -> str:
    edit_dir = edit_dir_for(video)
    out_dir = edit_dir / "analysis" / video.stem
    out_dir.mkdir(parents=True, exist_ok=True)

    meta = summarize_probe(probe(video))
    dur = meta["duration"]
    lines = [f"## {video.name}", ""]
    if "width" in meta:
        lines.append(f"- {meta['width']}x{meta['height']} {meta['orientation']}, {meta['fps']} fps, "
                     f"{meta['codec']} {meta['pix_fmt']}{', HDR' if meta['hdr'] else ''}"
                     f"{', rotated ' + str(meta['rotation']) if meta['rotation'] else ''}")
    lines.append(f"- duration {tc(dur)} ({dur:.1f}s), {meta['size_mb']:.1f} MB, {meta['bitrate_kbps']} kbps")
    lines.append(f"- audio: {', '.join(meta['audio_tracks']) or 'none'}")

    if meta["audio_tracks"]:
        a = audio_stats(video)
        silent = sum(e - s for s, e in a["silences"])
        lines.append(f"- loudness {a.get('lufs', '?')} LUFS, LRA {a.get('lra', '?')} LU, "
                     f"true peak {a.get('true_peak', '?')} dBFS "
                     f"(delivery target -14 LUFS / -1 dBTP)")
        lines.append(f"- silence ≥0.6s: {len(a['silences'])} gaps, {silent:.1f}s total "
                     f"({silent / dur:.0%} of runtime)" if dur else "")
        long_gaps = [(s, e) for s, e in a["silences"] if e - s >= 1.5]
        if long_gaps:
            lines.append("- long silences: " + ", ".join(f"{tc(s)}–{tc(e)}" for s, e in long_gaps[:20]))

    if video.suffix.lower() in VIDEO_EXTS and "width" in meta:
        scenes = detect_scenes(video, args.threshold, dur)
        lines.append(f"- scenes: {len(scenes)} (content threshold {args.threshold})")
        picks = scenes
        if len(picks) > args.max_frames:  # evenly sample scenes
            step = len(picks) / args.max_frames
            picks = [picks[int(i * step)] for i in range(args.max_frames)]
        frames: list[tuple[Path, str]] = []
        for i, (s, e) in enumerate(picks):
            t = s + (e - s) / 2
            dest = out_dir / f"scene_{i:03d}.jpg"
            if grab_frame(video, t, dest, args.width):
                frames.append((dest, f"#{i} {tc(s)}-{tc(e)}"))
        if frames:
            cols = 4 if meta["orientation"] == "horizontal" else 6
            contact_sheet(frames, out_dir / "contact.jpg", min(cols, len(frames)))
            lines.append(f"- contact sheet: `{(out_dir / 'contact.jpg').relative_to(edit_dir)}`")
        lines += ["", "| # | start | end | length |", "|---|---|---|---|"]
        lines += [f"| {i} | {tc(s)} | {tc(e)} | {e - s:.1f}s |" for i, (s, e) in enumerate(scenes[:200])]
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("targets", nargs="+", type=Path)
    ap.add_argument("--threshold", type=float, default=27.0, help="Scene cut sensitivity (lower = more cuts)")
    ap.add_argument("--max-frames", type=int, default=24, help="Frames on each contact sheet")
    ap.add_argument("--width", type=int, default=360, help="Thumbnail width in px")
    args = ap.parse_args()

    reports: dict[Path, list[str]] = {}
    for target in args.targets:
        for video in find_sources(target):
            print(f"analyzing {video.name}", flush=True)
            reports.setdefault(edit_dir_for(video), []).append(analyze(video, args))

    for edit_dir, sections in reports.items():
        out = edit_dir / "analysis.md"
        out.write_text("# Footage analysis\n\n" + "\n".join(sections), encoding="utf-8")
        print(f"wrote {out}")


if __name__ == "__main__":
    main()
