"""Audio for the SOGIXEL testimonial -> edit/mix.wav (48 kHz stereo, -14 LUFS, -1.5 dBTP).

1. Voice: left channel (lav; the right channel is a -40 dB camera mic; the
   iPhone CTA is dual mono), cut on the same frames as the picture, 30 ms
   fades at every join. The hook range plays C2408's sound under the C2406
   smile (range["audio"]), so C2408 runs as one continuous track.
2. Each source is levelled to the same speech loudness before the chain (the
   iPhone CTA is ~3 dB quieter than the lav).
3. Voice chain: rumble filter, light denoise, de-ess, compression, warmth,
   presence, air, limiter.
4. No music (brief). Two soft UI sounds: the name card and the CTA button.
5. Master: two-pass loudnorm to -14 LUFS / -1.5 dBTP.

    studio/.venv/bin/python edit/build_audio.py
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import wave
from pathlib import Path

import numpy as np

sys.path.insert(0, "/home/user/sxl/studio/bin")
import sfx  # noqa: E402

EDIT = Path(__file__).resolve().parent
OUT = EDIT
TL = json.loads((OUT / "timeline.json").read_text())
EV = json.loads(re.sub(r"^window\.EV = |;\s*$", "", (EDIT / "animations/overlay/events.js").read_text()))
SRC = EDIT.parent / "source"
SR = 48000
FADE = int(0.03 * SR)
EDL = json.loads((EDIT / "edl.json").read_text())
PATHS = {k: Path(v) for k, v in EDL["sources"].items()}
PATHS["C2408"] = SRC / "C2408.MP4"          # the hook borrows its sound
SPEECH_LUFS = -20.0        # every source is levelled to this before the chain

VOICE_CHAIN = ",".join([
    "highpass=f=80:poles=2",
    "afftdn=nr=8:nf=-48:tn=1",
    "deesser=i=0.35:m=0.5:f=0.5",
    "acompressor=threshold=-22dB:ratio=3:attack=6:release=110:makeup=3dB:knee=4",
    "equalizer=f=180:t=q:w=1.0:g=1.5",
    "equalizer=f=3300:t=q:w=1.3:g=2.5",
    "treble=g=1.5:f=9500",
    "alimiter=limit=0.9:level=disabled",
])


def read_wav(path: Path) -> np.ndarray:
    with wave.open(str(path)) as w:
        x = np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float32) / 32768
        return x.reshape(-1, w.getnchannels())


def write_wav(path: Path, x: np.ndarray) -> None:
    sfx.write_wav(path, x if x.ndim == 2 else x[:, None])


def ffmpeg_pcm(args: list[str], channels: int) -> np.ndarray:
    raw = subprocess.run(["ffmpeg", "-v", "error", *args, "-f", "s16le", "-ac", str(channels),
                          "-ar", str(SR), "-"], capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.int16).astype(np.float32).reshape(-1, channels) / 32768


def source_audio(clip: str, start: float, n: int) -> np.ndarray:
    x = ffmpeg_pcm(["-ss", f"{start:.4f}", "-i", str(PATHS[clip]), "-map", "0:a:0", "-af", "pan=mono|c0=c0",
                    "-t", f"{n / SR + 0.05:.4f}"], 1)[:n, 0]
    return np.pad(x, (0, n - len(x)))


def build_voice() -> np.ndarray:
    parts, owners = [], []
    for r in TL["ranges"]:
        n = r["frames"] * SR // TL["fps"]
        au = r.get("audio")
        clip, start = (au["source"], au["start"]) if au else (r["source"], r["src_start"])
        parts.append(source_audio(clip, start, n))
        owners.append(clip)
    # level each source on its own kept speech
    for clip in sorted(set(owners)):
        x = np.concatenate([p for p, o in zip(parts, owners) if o == clip])
        g = SPEECH_LUFS - lufs(np.repeat(x[:, None], 2, axis=1))
        print(f"  {clip}: {g:+.1f} dB")
        for k, o in enumerate(owners):
            if o == clip:
                parts[k] = parts[k] * 10 ** (g / 20)
    ramp = np.linspace(0, 1, FADE)
    for k, x in enumerate(parts):
        if k and owners[k] == owners[k - 1] and TL["ranges"][k - 1].get("audio") and not TL["ranges"][k].get("audio"):
            x[:FADE] *= 1                         # hook -> C2408: same continuous track, no dip
        else:
            x[:FADE] *= ramp
        if not (k + 1 < len(parts) and TL["ranges"][k].get("audio") and owners[k + 1] == owners[k]):
            x[-FADE:] *= ramp[::-1]
    return np.concatenate(parts)


def place(track: np.ndarray, clip: np.ndarray, t: float, gain_db: float, end_aligned: bool = False) -> None:
    g = 10 ** (gain_db / 20)
    i = int(round(t * SR)) - (len(clip) if end_aligned else 0)
    j0, j1 = max(i, 0), min(i + len(clip), len(track))
    if j1 > j0:
        track[j0:j1] += clip[j0 - i:j1 - i] * g


def build_sfx(n: int) -> np.ndarray:
    """Two soft UI sounds, nothing else: this one should feel natural."""
    tr = np.zeros((n, 2), np.float32)
    place(tr, sfx.pop(0.95), EV["name_in"], -24)
    place(tr, sfx.pop(1.1), EV["cta_btn"], -23)
    return tr


def run_af(x: np.ndarray, af: str, channels: int) -> np.ndarray:
    tmp_in, tmp_out = EDIT / "verify" / "_in.wav", EDIT / "verify" / "_out.wav"
    write_wav(tmp_in, x)
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(tmp_in), "-af", af, "-ar", str(SR),
                    "-ac", str(channels), str(tmp_out)], check=True)
    y = read_wav(tmp_out)
    tmp_in.unlink(); tmp_out.unlink()
    return y


def lufs(x: np.ndarray) -> float:
    tmp = EDIT / "verify" / "_lufs.wav"
    write_wav(tmp, x)
    err = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(tmp), "-af", "ebur128", "-f", "null", "-"],
                         capture_output=True, text=True).stderr
    tmp.unlink()
    return float(re.findall(r"I:\s+(-?[\d.]+) LUFS", err)[-1])


def loudnorm(x: np.ndarray) -> np.ndarray:
    tmp = EDIT / "verify" / "_mix.wav"
    write_wav(tmp, x)
    err = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(tmp), "-af",
                          "loudnorm=I=-14:TP=-1.5:LRA=11:print_format=json", "-f", "null", "-"],
                         capture_output=True, text=True).stderr
    m = json.loads(re.findall(r"\{[^{}]+\}", err)[-1])
    af = (f"loudnorm=I=-14:TP=-1.5:LRA=11:measured_I={m['input_i']}:measured_TP={m['input_tp']}:"
          f"measured_LRA={m['input_lra']}:measured_thresh={m['input_thresh']}:offset={m['target_offset']}:linear=true")
    y = run_af(x, af, 2)
    tmp.unlink()
    return y


def main() -> None:
    (EDIT / "verify").mkdir(exist_ok=True)
    voice_raw = build_voice()
    n = len(voice_raw)
    voice = run_af(voice_raw, VOICE_CHAIN, 1)[:n, 0]
    voice = np.pad(voice, (0, n - len(voice)))
    write_wav(EDIT / "verify" / "voice.wav", voice)
    mix = np.repeat(voice[:, None], 2, axis=1) + build_sfx(n)
    out = loudnorm(mix)[:n]
    write_wav(OUT / "mix.wav", out)
    print(f"mix.wav: {n / SR:.3f}s (no music)")


if __name__ == "__main__":
    main()
