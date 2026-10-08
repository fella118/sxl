"""Cut a source passage out of an already rendered reel (no 4K sources needed).

The raw clips of this project are off disk (Drive folder in project.md), so a
late content cut is applied to the rendered assets instead of re-running
cut.py + render_base.py: the same output frames are removed from base.mp4,
mask.mkv, facepos.json and mix.wav (30 ms crossfade, like a range join), and
timeline.json / edl.json are rewritten so events.py cues the new times.

    REEL=q2 studio/.venv/bin/python edit/trim_rendered.py C2426 40.04 42.75

Removes source [a, b) of the clip: the range holding a is trimmed to end at a,
ranges inside are dropped, a range holding b starts at b. a and b must be on
the 50 fps grid.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import wave
from pathlib import Path

import numpy as np

EDIT = Path(__file__).resolve().parent
REEL = os.environ["REEL"]
D = EDIT / REEL
FADE_S = 0.03


def new_ranges(tl: dict, clip: str, a: float, b: float) -> tuple[list, list[tuple[int, int]]]:
    """Ranges after the cut, and the removed output frame spans [f0, f1)."""
    fps, out, cuts, shift = tl["fps"], [], [], 0
    for r in tl["ranges"]:
        o0 = round(r["out_start"] * fps)
        n = r["frames"]
        r = dict(r)
        if r["source"] == clip and r.get("speed", 1.0) == 1.0 and r["src_end"] > a and r["src_start"] < b:
            keep_head = max(0, min(n, round((a - r["src_start"]) * fps)))
            keep_tail_from = max(0, min(n, round((b - r["src_start"]) * fps)))
            if keep_head > 0 and keep_tail_from >= n:         # trimmed at its end
                cuts.append((o0 + keep_head, o0 + n))
                r.update(src_end=round(r["src_start"] + keep_head / fps, 3), frames=keep_head)
            elif keep_head == 0 and keep_tail_from >= n:      # inside the cut: dropped
                cuts.append((o0, o0 + n))
                shift += n
                continue
            elif keep_head == 0:                              # starts inside the cut
                cuts.append((o0, o0 + keep_tail_from))
                r.update(src_start=round(r["src_start"] + keep_tail_from / fps, 3), frames=n - keep_tail_from)
            else:
                sys.exit("cut inside a single range is not supported; split it in cut.py")
            removed = n - r["frames"]
        else:
            removed = 0
        r["out_start"] = round((o0 - shift) / fps, 3)
        r["duration"] = round(r["frames"] / fps, 3)
        shift += removed
        out.append(r)
    return out, cuts


def keep_mask(total: int, cuts: list[tuple[int, int]]) -> np.ndarray:
    keep = np.ones(total, bool)
    for f0, f1 in cuts:
        keep[f0:f1] = False
    return keep


def cut_video(src: Path, dst: Path, keep: np.ndarray, codec: list[str], pix: str) -> None:
    frames = np.flatnonzero(keep)
    expr = "+".join(f"between(n\\,{s}\\,{e})" for s, e in spans(frames))
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(src), "-vf", f"select='{expr}',setpts=N/FRAME_RATE/TB",
                    "-pix_fmt", pix, *codec, str(dst)], check=True)


def spans(frames: np.ndarray) -> list[tuple[int, int]]:
    out, s = [], frames[0]
    for p, q in zip(frames, frames[1:]):
        if q != p + 1:
            out.append((s, p)); s = q
    out.append((s, frames[-1]))
    return out


def cut_audio(src: Path, dst: Path, cuts: list[tuple[int, int]], fps: int) -> None:
    with wave.open(str(src)) as w:
        sr, ch, width = w.getframerate(), w.getnchannels(), w.getsampwidth()
        x = np.frombuffer(w.readframes(w.getnframes()), np.int16).reshape(-1, ch).astype(np.float32)
    fade = int(FADE_S * sr)
    parts, prev = [], 0
    for f0, f1 in sorted(cuts):
        parts.append(x[prev:int(round(f0 / fps * sr))]); prev = int(round(f1 / fps * sr))
    parts.append(x[prev:])
    ramp = np.linspace(0, 1, fade)[:, None]                  # 30 ms fade out / in at each join, as a range join
    for k in range(len(parts)):                               # (no overlap: the length stays frame-exact)
        if k:
            parts[k][:fade] *= ramp
        if k + 1 < len(parts):
            parts[k][-fade:] *= ramp[::-1]
    y = np.concatenate(parts)
    with wave.open(str(dst), "wb") as w:
        w.setnchannels(ch); w.setsampwidth(width); w.setframerate(sr)
        w.writeframes(np.clip(y, -32768, 32767).astype(np.int16).tobytes())


def main() -> None:
    clip, a, b = sys.argv[1], float(sys.argv[2]), float(sys.argv[3])
    tl = json.loads((D / "timeline.json").read_text())
    fps = tl["fps"]
    total = round(tl["duration"] * fps)
    ranges, cuts = new_ranges(tl, clip, a, b)
    merged: list[tuple[int, int]] = []                        # adjacent spans (a trimmed range + a dropped one) join
    for f0, f1 in sorted(cuts):
        if merged and f0 <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], f1))
        else:
            merged.append((f0, f1))
    cuts = merged
    keep = keep_mask(total, cuts)
    removed = int((~keep).sum())
    print(f"{REEL}: removing {removed} frames ({removed / fps:.2f}s) at output frames {cuts}")

    bak = D / "pre_trim"
    bak.mkdir(exist_ok=True)
    for name in ("timeline.json", "edl.json", "facepos.json", "mix.wav"):
        shutil.copy2(D / name, bak / name)
    cut_video(D / "base.mp4", D / "base_trim.mp4", keep,
              ["-c:v", "libx264", "-preset", "fast", "-crf", "12", "-color_primaries", "bt709",
               "-color_trc", "bt709", "-colorspace", "bt709"], "yuv420p")
    cut_video(D / "mask.mkv", D / "mask_trim.mkv", keep, ["-c:v", "ffv1"], "gray")
    (D / "base.mp4").replace(bak / "base.mp4")                # originals kept, so the trim can be undone
    (D / "mask.mkv").replace(bak / "mask.mkv")
    (D / "base_trim.mp4").replace(D / "base.mp4")
    (D / "mask_trim.mkv").replace(D / "mask.mkv")
    fp = json.loads((D / "facepos.json").read_text())
    fp["frames"] = [f for f, k in zip(fp["frames"], keep) if k]
    (D / "facepos.json").write_text(json.dumps(fp))
    cut_audio(bak / "mix.wav", D / "mix.wav", cuts, fps)

    # timeline words: drop the cut ones, shift the rest by the frames removed before them
    def to_new(t: float) -> float | None:
        f = int(round(t * fps))
        if f < total and not keep[min(f, total - 1)]:
            return None
        return round(t - int((~keep[:f]).sum()) / fps, 3)

    def end_new(t: float) -> float:
        """A word that ends inside the cut now ends at the cut."""
        f = min(int(round(t * fps)), total)
        while f > 0 and not keep[f - 1]:
            f -= 1
        return round(min(t * fps, f) / fps - int((~keep[:f]).sum()) / fps, 3)
    words = []
    for w in tl["words"]:
        s = to_new(w["start"])
        if s is None or (w["id"].startswith(clip) and a - 0.01 <= w["src"] < b):
            continue
        words.append({**w, "start": s, "end": max(s, end_new(w["end"]))})
    dur = round((total - removed) / fps, 3)
    tl.update(ranges=ranges, words=words, duration=dur)
    (D / "timeline.json").write_text(json.dumps(tl, ensure_ascii=False, indent=1), encoding="utf-8")
    edl = json.loads((D / "edl.json").read_text())
    edl["ranges"] = [{"source": r["source"], "start": r["src_start"], "end": r["src_end"], "beat": r["beat"]} for r in ranges]
    edl["total_duration_s"] = dur
    (D / "edl.json").write_text(json.dumps(edl, indent=1), encoding="utf-8")
    print(f"{REEL}: {len(ranges)} ranges, {len(words)} words, {dur:.2f}s (backup in {bak.name}/)")


if __name__ == "__main__":
    main()
