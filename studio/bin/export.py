"""Export delivery masters per platform from a finished edit.

Reframes to the platform's aspect, normalizes loudness (two-pass loudnorm to
-14 LUFS / -1 dBTP), encodes H.264 + AAC with faststart, and writes a poster
frame. Outputs land in <project>/deliver/.

Presets:  reels (9:16 1080x1920, also TikTok/Shorts), feed (4:5 1080x1350),
          square (1:1 1080x1080), youtube (16:9 1920x1080), youtube4k (3840x2160)
Reframe:  crop     fill the frame, crop the overflow (--focus-x to aim, 0..1)
          blur     fit inside, fill the bars with a blurred copy
          pad      fit inside, black bars

Usage:
    python studio/bin/export.py projects/acme/launch/edit/final.mp4 reels youtube
    python studio/bin/export.py final.mp4 reels --reframe blur
    python studio/bin/export.py final.mp4 reels --reframe crop --focus-x 0.35 --poster 3.2
    python studio/bin/export.py edit/clean.mp4 reels --subs edit/master.srt
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from studio_paths import project_dir_for  # noqa: E402

PRESETS = {
    "reels": (1080, 1920),
    "feed": (1080, 1350),
    "square": (1080, 1080),
    "youtube": (1920, 1080),
    "youtube4k": (3840, 2160),
}

# Bold white, black outline, raised clear of the platform UI (same idea as video-use).
SUB_STYLE = ("FontName=DejaVu Sans,FontSize=16,Bold=1,PrimaryColour=&H00FFFFFF,"
             "OutlineColour=&H00000000,BorderStyle=1,Outline=2,Shadow=0,Alignment=2,MarginV=70")


def video_filter(w: int, h: int, mode: str, focus_x: float) -> str:
    if mode == "crop":
        return (f"scale={w}:{h}:force_original_aspect_ratio=increase,"
                f"crop={w}:{h}:(iw-{w})*{focus_x}:(ih-{h})/2,setsar=1")
    if mode == "pad":
        return (f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
                f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:black,setsar=1")
    # blur: fitted foreground over a blurred, filled background
    return (f"split[bg][fg];"
            f"[bg]scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},"
            f"gblur=sigma=40,eq=brightness=-0.08[bgb];"
            f"[fg]scale={w}:{h}:force_original_aspect_ratio=decrease[fgs];"
            f"[bgb][fgs]overlay=(W-w)/2:(H-h)/2,setsar=1")


def has_audio(path: Path) -> bool:
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries",
                          "stream=index", "-of", "csv=p=0", str(path)], capture_output=True, text=True)
    return bool(out.stdout.strip())


def measure_loudness(path: Path, target: float) -> dict:
    err = subprocess.run(
        ["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-vn",
         "-af", f"loudnorm=I={target}:TP=-1:LRA=11:print_format=json", "-f", "null", "-"],
        capture_output=True, text=True,
    ).stderr
    return json.loads(re.findall(r"\{[^{}]+\}", err)[-1])


def export(src: Path, preset: str, args) -> Path:
    w, h = PRESETS[preset]
    out_dir = args.out_dir or project_dir_for(src) / "deliver"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{args.name or src.stem}_{preset}.mp4"

    vf = video_filter(w, h, args.reframe, args.focus_x)
    if args.fps:
        vf += f",fps={args.fps}"
    if args.subs:
        # Burned after the reframe so captions are sized and placed for this aspect.
        srt = str(args.subs.resolve()).replace("\\", "/").replace(":", "\\:").replace("'", "\\'")
        vf += f",subtitles='{srt}':force_style='{args.sub_style}'"
    cmd = ["ffmpeg", "-y", "-v", "error", "-stats", "-i", str(src)]
    if ";" in vf or "split" in vf:
        cmd += ["-filter_complex", f"[0:v]{vf}[v]", "-map", "[v]"]
    else:
        cmd += ["-vf", vf, "-map", "0:v:0"]

    if has_audio(src):
        m = measure_loudness(src, args.lufs)
        af = (f"loudnorm=I={args.lufs}:TP=-1:LRA=11:measured_I={m['input_i']}:"
              f"measured_TP={m['input_tp']}:measured_LRA={m['input_lra']}:"
              f"measured_thresh={m['input_thresh']}:offset={m['target_offset']}:linear=true")
        cmd += ["-map", "0:a:0", "-af", af, "-c:a", "aac", "-b:a", "192k", "-ar", "48000"]

    cmd += ["-c:v", "libx264", "-preset", args.preset_speed, "-crf", str(args.crf),
            "-profile:v", "high", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(out)]
    print(f"{preset}: {w}x{h} [{args.reframe}] -> {out}", flush=True)
    subprocess.run(cmd, check=True)

    poster = out.with_suffix(".jpg")
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", str(args.poster), "-i", str(out),
                    "-frames:v", "1", "-q:v", "2", str(poster)], check=True)
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("input", type=Path)
    ap.add_argument("presets", nargs="+", choices=sorted(PRESETS))
    ap.add_argument("--reframe", choices=["crop", "blur", "pad"], default=None,
                    help="Default: crop when the aspect is close, blur when it changes orientation")
    ap.add_argument("--focus-x", type=float, default=0.5, help="Horizontal crop aim, 0=left 1=right")
    ap.add_argument("--lufs", type=float, default=-14.0)
    ap.add_argument("--crf", type=int, default=18)
    ap.add_argument("--preset-speed", default="slow", help="x264 preset (veryfast for drafts)")
    ap.add_argument("--fps", default=None, help="Force output fps, e.g. 30")
    ap.add_argument("--subs", type=Path, default=None,
                    help="Burn this SRT after reframing (render the master with --no-subtitles)")
    ap.add_argument("--sub-style", default=SUB_STYLE, help="libass force_style for --subs")
    ap.add_argument("--poster", type=float, default=1.0, help="Poster frame time in seconds")
    ap.add_argument("--name", default=None, help="Output basename (default: input stem)")
    ap.add_argument("--out-dir", type=Path, default=None)
    args = ap.parse_args()

    src = args.input.resolve()
    probe = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                            "stream=width,height", "-of", "csv=p=0", str(src)],
                           capture_output=True, text=True, check=True).stdout.strip().split(",")
    src_vertical = int(probe[1]) > int(probe[0])
    chosen = args.reframe
    for preset in args.presets:
        w, h = PRESETS[preset]
        if chosen is None:
            args.reframe = "blur" if (h > w) != src_vertical and w != h else "crop"
        export(src, preset, args)


if __name__ == "__main__":
    main()
