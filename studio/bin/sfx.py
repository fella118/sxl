"""Synthesized UI/motion sound effects (no stock assets, no licensing).

Each function returns a float32 stereo array at 48 kHz, peak about -1 dBFS,
with the transient at sample 0 unless noted (risers end on their last sample).

    from sfx import SR, pop, key, whoosh, tick, impact, riser, ding, buzz
    python studio/bin/sfx.py out_dir      # writes one wav per effect to audition
"""

from __future__ import annotations

import sys
import wave
from pathlib import Path

import numpy as np
from scipy import signal

SR = 48000
RNG = np.random.default_rng(7)


def _t(d: float) -> np.ndarray:
    return np.arange(int(d * SR)) / SR


def _norm(x: np.ndarray, peak: float = 0.89) -> np.ndarray:
    m = np.max(np.abs(x)) or 1.0
    return (x / m * peak).astype(np.float32)


def _stereo(x: np.ndarray, pan: float | np.ndarray = 0.0) -> np.ndarray:
    pan = np.clip(pan, -1, 1)
    l, r = np.cos((pan + 1) * np.pi / 4), np.sin((pan + 1) * np.pi / 4)
    return np.stack([x * l, x * r], axis=1).astype(np.float32)


def _band(x: np.ndarray, lo: float, hi: float, order: int = 4) -> np.ndarray:
    sos = signal.butter(order, [lo, hi], btype="band", fs=SR, output="sos")
    return signal.sosfilt(sos, x)


def _env(n: int, attack: float, decay: float) -> np.ndarray:
    t = np.arange(n) / SR
    a = np.clip(t / max(attack, 1e-4), 0, 1)
    return a * np.exp(-np.maximum(t - attack, 0) / decay)


def pop(pitch: float = 1.0) -> np.ndarray:
    """Bubbly UI pop: fast downward pitch sweep plus a soft click."""
    t = _t(0.12)
    f = (950 * pitch) * np.exp(-t * 28) + 260 * pitch
    body = np.sin(2 * np.pi * np.cumsum(f) / SR) * _env(len(t), 0.002, 0.035)
    click = _band(RNG.standard_normal(len(t)), 2500, 9000) * _env(len(t), 0.0005, 0.004) * 0.35
    return _stereo(_norm(body + click))


def key(pitch: float = 1.0) -> np.ndarray:
    """Phone keyboard tap."""
    t = _t(0.05)
    tap = _band(RNG.standard_normal(len(t)), 1800 * pitch, 7000) * _env(len(t), 0.0004, 0.006)
    thock = np.sin(2 * np.pi * 210 * pitch * t) * _env(len(t), 0.001, 0.012) * 0.5
    return _stereo(_norm(tap + thock, 0.7))


def whoosh(dur: float = 0.45, pan_from: float = -0.6, pan_to: float = 0.6) -> np.ndarray:
    """Air whoosh: noise through a band that sweeps up and back, panning across."""
    n = int(dur * SR)
    noise = RNG.standard_normal(n)
    f, tt, z = signal.stft(noise, SR, nperseg=1024)
    pos = tt / tt[-1]
    centre = 350 + 2600 * np.sin(np.pi * pos) ** 1.5
    shape = np.exp(-((f[:, None] - centre[None, :]) / (0.6 * centre[None, :])) ** 2)
    _, x = signal.istft(z * shape, SR, nperseg=1024)
    x = x[:n]
    env = np.sin(np.pi * np.clip(np.arange(n) / n, 0, 1)) ** 2.2
    return _stereo(_norm(x * env, 0.8), np.linspace(pan_from, pan_to, n))


def tick(pitch: float = 1.0) -> np.ndarray:
    """Checkbox tick: short bright tone with a click."""
    t = _t(0.09)
    tone = (np.sin(2 * np.pi * 1900 * pitch * t) + 0.4 * np.sin(2 * np.pi * 3800 * pitch * t)) * _env(len(t), 0.001, 0.022)
    click = _band(RNG.standard_normal(len(t)), 3000, 10000) * _env(len(t), 0.0003, 0.002) * 0.4
    return _stereo(_norm(tone + click, 0.75))


def impact() -> np.ndarray:
    """Low cinematic hit."""
    t = _t(0.7)
    f = 75 * np.exp(-t * 3) + 38
    boom = np.sin(2 * np.pi * np.cumsum(f) / SR) * _env(len(t), 0.003, 0.22)
    lo = signal.sosfilt(signal.butter(4, 900, fs=SR, output="sos"), RNG.standard_normal(len(t)))
    crack = lo * _env(len(t), 0.001, 0.05) * 0.6
    return _stereo(_norm(boom + crack))


def riser(dur: float = 1.6) -> np.ndarray:
    """Tension riser ending on its last sample (place its end on the hit)."""
    t = _t(dur)
    f = 180 * (7 ** (t / dur))
    tone = np.sin(2 * np.pi * np.cumsum(f) / SR) * 0.35
    air = _band(RNG.standard_normal(len(t)), 1500, 9000) * 0.5
    env = (t / dur) ** 2.4
    fade = np.minimum(1, (dur - t) / 0.01)
    return _stereo(_norm((tone + air) * env * fade, 0.8))


def ding() -> np.ndarray:
    """Notification chime: two bell partials, second slightly later."""
    t = _t(0.9)
    def bell(f0, delay):
        tt = np.maximum(t - delay, 0)
        on = (t >= delay).astype(float)
        return on * (np.sin(2 * np.pi * f0 * tt) + 0.35 * np.sin(2 * np.pi * 2.76 * f0 * tt)) * np.exp(-tt / 0.28)
    return _stereo(_norm(bell(1318.5, 0) + 0.85 * bell(1760, 0.09), 0.8))


def buzz() -> np.ndarray:
    """Wrong-answer buzz plus a soft thud."""
    t = _t(0.22)
    sq = signal.square(2 * np.pi * 140 * t) * 0.4 + signal.square(2 * np.pi * 147 * t) * 0.4
    sq = signal.sosfilt(signal.butter(2, 1800, fs=SR, output="sos"), sq) * _env(len(t), 0.003, 0.09)
    thud = np.sin(2 * np.pi * 70 * t) * _env(len(t), 0.002, 0.06)
    return _stereo(_norm(sq + thud, 0.8))


def write_wav(path: Path, x: np.ndarray) -> None:
    pcm = (np.clip(x, -1, 1) * 32767).astype(np.int16)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(pcm.shape[1] if pcm.ndim == 2 else 1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())


if __name__ == "__main__":
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "sfx")
    out.mkdir(parents=True, exist_ok=True)
    for name, fn in {"pop": pop, "key": key, "whoosh": whoosh, "tick": tick, "impact": impact,
                     "riser": riser, "ding": ding, "buzz": buzz}.items():
        write_wav(out / f"{name}.wav", fn())
    print(f"wrote effects to {out}")
