"""Audio for Reel 02 (Q&A) -> edit/mix.wav (48 kHz stereo, -14 LUFS, -1.5 dBTP).

1. Voice: left channel only (lav; the right channel is a -40 dB camera mic),
   cut on the same frames as the picture, 30 ms fades at every join.
2. Voice chain: rumble filter, light denoise, de-ess, compression, warmth,
   presence, air, limiter.
3. SFX: synthesized (studio/bin/sfx.py), each one on a visible event (quiz-show set).
4. Music (optional): drop the client's track at source/music/track.* (any format)
   and set MUSIC_START; it is ducked under the voice and levelled by measurement.
5. Master: two-pass loudnorm to -14 LUFS / -1 dBTP.

    REEL=q1 studio/.venv/bin/python edit/build_audio.py [--no-music]
"""

from __future__ import annotations

import argparse
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
REEL = os.environ["REEL"]
OUT = EDIT / REEL
TL = json.loads((OUT / "timeline.json").read_text())
EV = json.loads(re.sub(r"^window\.EV = |;\s*$", "", (EDIT / f"animations/overlay/events_{REEL}.js").read_text()))
SRC = EDIT.parent / "source"
SR = 48000
FADE = int(0.03 * SR)
MUSIC_START = 0.0          # seconds into the track (set when the client's track arrives)
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
    """Playful quiz-show layer: one effect per visible event."""
    tr = np.zeros((n, 2), np.float32)
    rng = np.random.default_rng(7)
    ar = lambda txt: any("\u0600" <= ch <= "\u06ff" for ch in txt)  # noqa: E731
    # question cards: whoosh in, pop, game-show ding, sparkle
    for q in EV["quiz"]:
        place(tr, sfx.whoosh(0.3, -0.4, 0.4), q["t"] - 0.12, -17)
        place(tr, sfx.pop(0.8), q["t"] + 0.02, -12)
        place(tr, sfx.ding(), q["t"] + 0.14, -15)
        place(tr, sfx.tick(1.45), q["t"] + 0.2, -19)
    for c in EV["chips"]:
        place(tr, sfx.pop(1.25), c["start"], -22)
    # answers: the "جواب" wall sweeps in behind him with a correct-answer ding
    for t0 in EV["walls"]:
        place(tr, sfx.whoosh(0.42, -0.7, 0.7), t0 - 0.08, -14)
        place(tr, sfx.ding(), t0 + 0.06, -14)
    # phrase typography: swish on keywords, tick on numbers (small/script words stay silent)
    for p in EV["phrases"]:
        for line in p["lines"]:
            for wd in line:
                if wd["role"] == "key":
                    place(tr, sfx.whoosh(0.22, -0.3, 0.3), wd["at"] - 0.12, -21)
                elif wd["role"] == "num":
                    place(tr, sfx.tick(1.05), wd["at"], -14)
    # punchlines (with the grey background)
    for a, _ in EV["gray"]:
        place(tr, sfx.impact(), a, -14)
    # Q1 price tag: drops on its string, lands, "DH" pops
    if "tag_in" in EV:
        place(tr, sfx.whoosh(0.35, 0.0, 0.0), EV["tag_in"] - 0.2, -17)
        place(tr, sfx.tick(0.75), EV["tag_in"] + 0.22, -15)
        place(tr, sfx.pop(1.3), EV["tag_dh"], -16)
    # close-ups (cutaways) and the camera tilt for the table
    for t in EV.get("cutaways", []):
        place(tr, sfx.whoosh(0.3, 0.5, -0.5), t - 0.15, -18)
    # A1: optician's speech bubble (taps on the typed words), white-card pointer
    if "said_in" in EV:
        place(tr, sfx.pop(1.0), EV["said_in"], -16)
        for k, (word, t) in enumerate([("درت", EV["said_in"] + 0.35), ("لك", EV["said_in"] + 0.55), ("l'indice", EV["said_type"])]):
            taps = 1 if ar(word) else len(word)
            for j in range(taps):
                place(tr, sfx.key(rng.uniform(0.85, 1.2)), t + 0.4 * j / taps, -21)
    if "callout_in" in EV:
        place(tr, sfx.pop(1.1), EV["callout_in"], -15)
        place(tr, sfx.tick(1.2), EV["callout_in"] + 0.4, -16)
    # A3: table pops in, headers tick, each row slides in and its index ticks
    if "table_in" in EV:
        place(tr, sfx.whoosh(0.4, -0.6, 0.2), EV["table_in"] - 0.15, -16)
        place(tr, sfx.pop(0.85), EV["table_in"] + 0.05, -15)
        for t in EV["hdr"]:
            place(tr, sfx.tick(0.9), t, -18)
        for i, r in enumerate(EV["rows"]):
            place(tr, sfx.whoosh(0.2, 0.6, -0.2), r["c"] - 0.14, -20)
            place(tr, sfx.tick(1.0 + 0.08 * i), r["i"], -13)
            if "m" in r:
                place(tr, sfx.pop(1.15), r["m"], -15)
    # A3: lens card flips in, name, pills, thin vs normal
    if "lens_in" in EV:
        place(tr, sfx.whoosh(0.45, 0.4, -0.4), EV["lens_in"] - 0.1, -16)
        place(tr, sfx.pop(0.9), EV["lens_name"], -15)
        for t in (EV["lens_org"] - 0.5, EV["lens_org"], EV["lens_plastic"]):
            place(tr, sfx.pop(1.2), t, -18)
        place(tr, sfx.pop(1.0), EV["lens_thin"], -16)
        place(tr, sfx.pop(0.8), EV["lens_normal"] - 0.2, -16)
        place(tr, sfx.ding(), EV["lens_normal"] + 0.15, -16)
    # A2: frame-arm diagram
    if "arm_in" in EV:
        place(tr, sfx.whoosh(0.4, -0.7, 0.5), EV["arm_in"] - 0.1, -16)
        place(tr, sfx.tick(1.1), EV["arm_digits"], -16)
        place(tr, sfx.whoosh(0.3, 0.2, -0.2), EV["arm_d"] - 0.05, -19)
        place(tr, sfx.buzz(), EV["arm_48"], -19)
        place(tr, sfx.ding(), EV["arm_46"], -13)
    # teaser card
    if "next_in" in EV:
        place(tr, sfx.whoosh(0.4, 0.0, 0.0), EV["next_in"] - 0.1, -16)
        place(tr, sfx.impact(), EV["next_case"], -16)
        place(tr, sfx.pop(0.95), EV["next_old"] - 0.3, -17)
        place(tr, sfx.pop(1.3), EV["next_new"], -15)
    # CTA: save button pops, gets tapped, fills, ding
    place(tr, sfx.pop(0.9), EV["save_in"], -14)
    place(tr, sfx.key(1.0), EV["save_fill"] - 0.05, -14)
    place(tr, sfx.pop(1.45), EV["save_fill"], -13)
    place(tr, sfx.ding(), EV["save_fill"] + 0.06, -12)
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
    write_wav(OUT / "mix.wav", out)
    print(f"mix.wav: {n / SR:.3f}s, music: {'yes' if music is not None else 'no (source/music/track.* missing)'}")


if __name__ == "__main__":
    main()
