"""Silero VAD speech probability per 10 ms for every clip -> edit/analysis_audio/<clip>_vad.npy.

Silero scores breaths, lip noise and room tone as non-speech, which is what the
breath/dead-air cut needs. Run with the Darija venv (it has silero_vad):

    studio/.venv-darija/bin/python edit/vad_probs.py
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import numpy as np
import torch
from silero_vad import load_silero_vad

EDIT = Path(__file__).resolve().parent
SRC = EDIT.parent / "source"
SR, CHUNK = 16000, 512   # 32 ms


def main() -> None:
    model = load_silero_vad()
    out = EDIT / "analysis_audio"
    out.mkdir(exist_ok=True)
    for mp4 in sorted(SRC.glob("C*.MP4")):
        raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(mp4), "-map", "0:a:0", "-af", "pan=mono|c0=c0",
                              "-ar", str(SR), "-f", "s16le", "-"], capture_output=True, check=True).stdout
        x = torch.from_numpy(np.frombuffer(raw, np.int16).astype(np.float32) / 32768)
        model.reset_states()
        probs = []
        for i in range(0, len(x) - CHUNK, CHUNK):
            probs.append(float(model(x[i:i + CHUNK], SR)))
        p = np.array(probs)
        t32 = (np.arange(len(p)) * CHUNK + CHUNK / 2) / SR       # chunk centres
        t10 = np.arange(int(len(x) / SR * 100)) / 100 + 0.005
        np.save(out / f"{mp4.stem}_vad.npy", np.interp(t10, t32, p).astype(np.float32))
        print(f"{mp4.stem}: {len(p)} chunks, speech {np.mean(p > 0.5) * 100:.0f}%")


if __name__ == "__main__":
    main()
