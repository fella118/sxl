"""Transcribe videos into video-use's Scribe-format JSON, then pack them.

Engines:
  local   faster-whisper on CPU (default). Needs huggingface.co reachable the
          first time a model is used; models are cached afterwards.
  scribe  ElevenLabs Scribe via video-use (best diarization). Needs
          ELEVENLABS_API_KEY and api.elevenlabs.io reachable.

Output per source: <edit>/transcripts/<stem>.json with a `words` list of
{type: word|spacing, text, start, end, speaker_id}, the same shape Scribe
returns, so video-use's pack_transcripts.py and render.py work unchanged.
Cached: an existing transcript is never redone unless --force.

Usage:
    python studio/bin/transcribe.py <project_dir | video> [...]
    python studio/bin/transcribe.py projects/acme/launch --language fr
    python studio/bin/transcribe.py clip.mp4 --model small   # quick draft
    python studio/bin/transcribe.py projects/acme/launch --engine scribe --num-speakers 2
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from studio_paths import VIDEO_USE_HELPERS, find_sources, edit_dir_for  # noqa: E402


def extract_audio(video: Path, dest: Path, audio_track: int) -> None:
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-i", str(video), "-map", f"0:a:{audio_track}",
         "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(dest)],
        check=True,
    )


def load_wav(path: Path):
    """16 kHz mono s16 wav -> float32 array. Passing samples skips faster-whisper's
    PyAV decoder, which breaks on some PyAV releases."""
    import wave

    import numpy as np

    with wave.open(str(path), "rb") as w:
        pcm = w.readframes(w.getnframes())
    return np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0


def to_scribe(segments, info) -> dict:
    """faster-whisper segments -> Scribe response shape (words + spacing)."""
    words: list[dict] = []
    prev_end: float | None = None
    for seg in segments:
        for w in seg.words or []:
            text = w.word.strip()
            if not text:
                continue
            if prev_end is not None and w.start > prev_end:
                words.append({"type": "spacing", "text": " ", "start": round(prev_end, 3),
                              "end": round(w.start, 3), "speaker_id": "speaker_0"})
            words.append({"type": "word", "text": text, "start": round(w.start, 3),
                          "end": round(w.end, 3), "speaker_id": "speaker_0",
                          "logprob": round(w.probability, 3)})
            prev_end = w.end
    return {
        "language_code": info.language,
        "language_probability": round(info.language_probability, 3),
        "text": " ".join(w["text"] for w in words if w["type"] == "word"),
        "words": words,
        "engine": "faster-whisper",
    }


def transcribe_local(video: Path, out: Path, args, model_cache: dict) -> None:
    from faster_whisper import WhisperModel

    if "model" not in model_cache:
        print(f"  loading model {args.model} (int8, cpu)", flush=True)
        try:
            model_cache["model"] = WhisperModel(args.model, device="cpu", compute_type="int8")
        except Exception as exc:  # download blocked or interrupted
            raise SystemExit(
                f"could not load whisper model '{args.model}': {type(exc).__name__}: {exc}\n"
                "The model downloads from huggingface.co (*.hf.co) on first use. Allow those "
                "hosts in the environment's network settings, or use --engine scribe."
            ) from None
    model = model_cache["model"]

    with tempfile.TemporaryDirectory() as tmp:
        wav = Path(tmp) / "a.wav"
        extract_audio(video, wav, args.audio_track)
        segments, info = model.transcribe(
            load_wav(wav),
            language=args.language,
            word_timestamps=True,
            vad_filter=True,
            vad_parameters={"min_silence_duration_ms": 300},
            # Verbatim: keep fillers and false starts, the editor needs them.
            initial_prompt=args.prompt or "Umm, uh, so, like, you know... I mean, I- I think.",
            condition_on_previous_text=False,
        )
        payload = to_scribe(list(segments), info)
    out.write_text(json.dumps(payload, indent=1, ensure_ascii=False))
    n = sum(1 for w in payload["words"] if w["type"] == "word")
    print(f"  {out.name}: {n} words, language {payload['language_code']} "
          f"({payload['language_probability']:.0%})")


def transcribe_scribe(video: Path, edit_dir: Path, args) -> None:
    sys.path.insert(0, str(VIDEO_USE_HELPERS))
    from transcribe import load_api_key, transcribe_one  # video-use

    transcribe_one(video=video, edit_dir=edit_dir, api_key=load_api_key(),
                   language=args.language, num_speakers=args.num_speakers,
                   audio_track=args.audio_track)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("targets", nargs="+", type=Path, help="Project dirs or video files")
    ap.add_argument("--engine", choices=["local", "scribe"], default="local")
    ap.add_argument("--model", default="large-v3-turbo",
                    help="faster-whisper model. large-v3-turbo (default) runs about 3x faster "
                         "than real time on this 4-core CPU; small is about 2x faster again "
                         "for quick drafts; large-v3 is the slowest and most accurate.")
    ap.add_argument("--language", default=None, help="ISO code (en, fr, ar, es...). Default: auto")
    ap.add_argument("--num-speakers", type=int, default=None, help="Scribe only")
    ap.add_argument("--audio-track", type=int, default=0)
    ap.add_argument("--prompt", default=None, help="Vocabulary hint: names, brands, jargon")
    ap.add_argument("--force", action="store_true", help="Redo cached transcripts")
    args = ap.parse_args()

    model_cache: dict = {}
    edit_dirs: set[Path] = set()
    for target in args.targets:
        for video in find_sources(target.resolve()):
            edit_dir = edit_dir_for(video)
            out = edit_dir / "transcripts" / f"{video.stem}.json"
            out.parent.mkdir(parents=True, exist_ok=True)
            edit_dirs.add(edit_dir)
            if out.exists() and not args.force:
                print(f"cached: {out}")
                continue
            if args.force and out.exists():
                out.unlink()
            print(f"transcribing {video.name} [{args.engine}]", flush=True)
            t0 = time.time()
            if args.engine == "local":
                transcribe_local(video, out, args, model_cache)
            else:
                transcribe_scribe(video, edit_dir, args)
            print(f"  done in {time.time() - t0:.1f}s")

    for edit_dir in sorted(edit_dirs):
        subprocess.run([sys.executable, str(VIDEO_USE_HELPERS / "pack_transcripts.py"),
                        "--edit-dir", str(edit_dir)], check=True)


if __name__ == "__main__":
    main()
