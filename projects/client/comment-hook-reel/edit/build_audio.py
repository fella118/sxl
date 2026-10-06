"""Audio for the comment hook reel -> edit/mix.wav (48 kHz stereo, -14 LUFS, -1 dBTP).

1. Voice: left channel only (lav; the right channel is a -40 dB camera mic),
   cut on the same frames as the picture, 30 ms fades at every join.
2. Voice chain: rumble filter, light denoise, de-ess, compression, warmth,
   presence, air, limiter.
3. SFX: synthesized (studio/bin/sfx.py), each one on a visible event.
4. Music (optional): source/music/track.* from MUSIC_START, ducked under voice.
5. Master: two-pass loudnorm to -14 LUFS / -1 dBTP.

    studio/.venv/bin/python edit/build_audio.py [--no-music]
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import wave
from pathlib import Path

import numpy as np

sys.path.insert(0, "/home/user/sxl/studio/bin")
import sfx  # noqa: E402

EDIT = Path(__file__).resolve().parent
TL = json.loads((EDIT / "timeline.json").read_text())
EV = json.loads(re.sub(r"^window\.EV = |;\s*$", "", (EDIT / "animations/overlay/events.js").read_text()))
SRC = EDIT.parent / "source"
SR = 48000
FADE = int(0.03 * SR)
MUSIC_START = 7.0          # seconds into the track: the instrumental entry
MUSIC_REL_LU = -11.0       # ducked music stem loudness relative to the voice stem (v2: more present)
MUSIC_DUCK_DB = -9.0       # reduction while he speaks

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


def build_voice() -> np.ndarray:
    parts = []
    for r in TL["ranges"]:
        n = r["frames"] * SR // TL["fps"]
        x = ffmpeg_pcm(["-ss", f"{r['src_start']:.4f}", "-i", str(SRC / f"{r['source']}.MP4"),
                        "-map", "0:a:0", "-af", "pan=mono|c0=c0", "-t", f"{n / SR + 0.05:.4f}"], 1)[:n, 0]
        x = np.pad(x, (0, n - len(x)))
        ramp = np.linspace(0, 1, FADE)
        x[:FADE] *= ramp
        x[-FADE:] *= ramp[::-1]
        parts.append(x)
    return np.concatenate(parts)


def place(track: np.ndarray, clip: np.ndarray, t: float, gain_db: float, end_aligned: bool = False) -> None:
    g = 10 ** (gain_db / 20)
    i = int(round(t * SR)) - (len(clip) if end_aligned else 0)
    j0, j1 = max(i, 0), min(i + len(clip), len(track))
    if j1 > j0:
        track[j0:j1] += clip[j0 - i:j1 - i] * g


def build_sfx(n: int) -> np.ndarray:
    """v3: one effect per visible event, quieter than v2."""
    tr = np.zeros((n, 2), np.float32)
    rng = np.random.default_rng(3)
    ar = lambda txt: any("\u0600" <= ch <= "\u06ff" for ch in txt)  # noqa: E731
    # hook card: pop, taps (one per Arabic word, one per French letter), reply, whoosh out
    place(tr, sfx.pop(0.9), EV["card_in"] + 0.02, -10)
    for w in EV["hook_words"]:
        d = max(0.12, w["end"] - w["start"])
        taps = 1 if ar(w["text"]) else len(w["text"])
        for k in range(taps):
            place(tr, sfx.key(rng.uniform(0.85, 1.2)), w["start"] + d * k / taps, -19 + rng.uniform(-2, 1))
    place(tr, sfx.pop(1.25), EV["reply"] - 0.15, -16)
    place(tr, sfx.whoosh(0.45, -0.4, 0.7), EV["card_out"] - 0.1, -14)
    # dizzy rings
    place(tr, sfx.whoosh(0.7, -0.8, 0.8), EV["rings_in"] - 0.05, -16)
    # phrase typography: swish on keywords, tick on numbers (small/script words stay silent)
    for p in EV["phrases"]:
        for line in p["lines"]:
            for wd in line:
                if wd["role"] == "key":
                    place(tr, sfx.whoosh(0.22, -0.3, 0.3), wd["at"] - 0.12, -21)
                elif wd["role"] == "num":
                    place(tr, sfx.tick(1.05), wd["at"], -14)
    # cutaway to the glasses
    cut_t = TL["ranges"][8]["out_start"]
    place(tr, sfx.whoosh(0.3, 0.5, -0.5), cut_t - 0.15, -17)
    # loin / pres cards -> X
    place(tr, sfx.whoosh(0.32, -0.8, -0.1), EV["loin"] - 0.3, -19)
    place(tr, sfx.whoosh(0.32, 0.8, 0.1), EV["pres"] - 0.3, -19)
    place(tr, sfx.buzz(), EV["sep"], -15)
    # chart: pop, riser into +3, hit
    place(tr, sfx.pop(0.85), EV["chart_in"], -17)
    place(tr, sfx.riser(max(0.4, EV["plus3"] - EV["bar2"])), EV["plus3"], -20, end_aligned=True)
    place(tr, sfx.impact(), EV["plus3"], -12)
    # "صعاب" wall + grayscale
    place(tr, sfx.impact(), EV["wall_in"], -13)
    # zoom out to the checklist
    zoom_out = next(w["start"] for w in TL["words"] if abs(w["src"] - 29.25) < 0.03) - 0.5
    place(tr, sfx.whoosh(0.5, 0.6, -0.6), zoom_out, -16)
    # criteria ticks
    place(tr, sfx.pop(1.0), EV["crit_in"], -17)
    for i, t in enumerate(EV["crit"]):
        place(tr, sfx.tick(1.0 + 0.06 * i), t, -13)
    # 3 days
    place(tr, sfx.pop(0.9), EV["days_in"], -16)
    place(tr, sfx.pop(1.3), EV["days_hit"], -13)
    # back -> centrage -> professional
    place(tr, sfx.pop(1.0), EV["back_in"], -16)
    place(tr, sfx.tick(1.1), EV["back_check"], -13)
    place(tr, sfx.whoosh(0.4, -0.5, 0.5), EV["pro"] - 0.3, -17)
    # CTA
    place(tr, sfx.pop(0.95), EV["cta_in"], -15)
    for k, word in enumerate(["سؤال", "على", "les", "progressifs؟"]):
        taps = 1 if ar(word) else len(word)
        for j in range(taps):
            place(tr, sfx.key(rng.uniform(0.85, 1.2)), EV["cta_type"] + k * 0.19 + 0.18 * j / taps, -21)
    place(tr, sfx.pop(1.4), EV["cta_send"], -14)
    place(tr, sfx.ding(), EV["cta_next"], -13)
    return tr


def run_af(x: np.ndarray, af: str, channels: int) -> np.ndarray:
    tmp_in, tmp_out = EDIT / "verify" / "_in.wav", EDIT / "verify" / "_out.wav"
    write_wav(tmp_in, x)
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(tmp_in), "-af", af, "-ar", str(SR),
                    "-ac", str(channels), str(tmp_out)], check=True)
    y = read_wav(tmp_out)
    tmp_in.unlink(); tmp_out.unlink()
    return y


def build_music(n: int, voice: np.ndarray) -> np.ndarray | None:
    tracks = sorted(SRC.glob("music/track.*"))
    if not tracks:
        return None
    m = ffmpeg_pcm(["-ss", str(MUSIC_START), "-i", str(tracks[0]), "-t", f"{n / SR:.3f}"], 2)
    m = np.pad(m, ((0, max(0, n - len(m))), (0, 0)))[:n]
    # duck under speech: follow the voice envelope (~12 dB of reduction while he talks)
    env = np.abs(voice)
    win = int(0.25 * SR)
    env = np.convolve(env, np.ones(win) / win, mode="same")
    speech = np.clip((20 * np.log10(env + 1e-6) + 45) / 15, 0, 1)
    k = int(0.15 * SR)
    speech = np.convolve(speech, np.ones(k) / k, mode="same")
    m *= (10 ** (MUSIC_DUCK_DB * speech / 20))[:, None]
    fade_in, fade_out = int(0.3 * SR), int(1.2 * SR)
    m[:fade_in] *= np.linspace(0, 1, fade_in)[:, None]
    m[-fade_out:] *= np.linspace(1, 0, fade_out)[:, None]
    # level by measurement: ducked music sits MUSIC_REL_LU under the voice
    gain = (lufs(np.repeat(voice[:, None], 2, axis=1)) + MUSIC_REL_LU) - lufs(m)
    print(f"  music gain {gain:+.1f} dB -> {MUSIC_REL_LU:+.0f} LU under the voice")
    return m * 10 ** (gain / 20)


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
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-music", action="store_true")
    args = ap.parse_args()

    voice_raw = build_voice()
    n = len(voice_raw)
    voice = run_af(voice_raw, VOICE_CHAIN, 1)[:n, 0]
    voice = np.pad(voice, (0, n - len(voice)))
    write_wav(EDIT / "verify" / "voice.wav", voice)
    mix = np.repeat(voice[:, None], 2, axis=1) + build_sfx(n)
    music = None if args.no_music else build_music(n, voice)
    if music is not None:
        mix += music
    if music is not None:
        for name, stem in (("voice", np.repeat(voice[:, None], 2, axis=1)), ("music", music)):
            write_wav(EDIT / "verify" / f"stem_{name}.wav", stem)
            err = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(EDIT / "verify" / f"stem_{name}.wav"),
                                  "-af", "ebur128", "-f", "null", "-"], capture_output=True, text=True).stderr
            print(f"  {name} stem: {re.findall(r'I:\s+(-?[\d.]+) LUFS', err)[-1]} LUFS")
    out = loudnorm(mix)[:n]
    write_wav(EDIT / "mix.wav", out)
    print(f"mix.wav: {n / SR:.3f}s, music: {'yes' if music is not None else 'no (source/music/track.* missing)'}")


if __name__ == "__main__":
    main()
