"""Darija/French transcription: Silero VAD -> MoulSot v0.3 -> MMS forced alignment.

Same pipeline as the local darija-transcribe skill:
  1. Silero VAD finds where someone is speaking.
  2. MoulSot v0.3 (atlasia, Qwen3-ASR fine-tune) writes the transcript:
     Darija in Arabic script, French in Latin letters.
  3. MMS forced alignment (torchaudio MMS_FA on uroman romanization) gives
     every word its start and end time.

Runs in its own venv (qwen-asr pins transformers): studio/.venv-darija.

Writes, per source:
  <edit>/transcripts/<stem>.json      Scribe-shaped words, for video-use (pack, render)
  <edit>/darija/<stem>.srt            phrase subtitles
  <edit>/darija/<stem>.txt            plain text, one VAD chunk per line
  <edit>/darija/<stem>.words.json     [{word, start, end, chunk}]
  <edit>/darija/<stem>.words.txt      "start<TAB>end<TAB>word" lines (motion-broll input)
then packs <edit>/takes_packed.md.

Usage:
    studio/.venv-darija/bin/python studio/bin/darija_transcribe.py <project_dir | video> [...]
    ... --context "progressifs, addition, opticien, centrage"   # vocabulary hint
    ... --force
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from studio_paths import VIDEO_USE_HELPERS, edit_dir_for, find_sources  # noqa: E402

SR = 16000
MODEL_ID = "atlasia/moulsot.v0.3"


def load_audio(video: Path, audio_track: int) -> np.ndarray:
    pcm = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(video), "-map", f"0:a:{audio_track}",
         "-ac", "1", "-ar", str(SR), "-f", "s16le", "-"],
        capture_output=True, check=True,
    ).stdout
    return np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0


def vad_chunks(audio: np.ndarray, max_chunk: float, min_gap: float) -> list[tuple[float, float]]:
    """Speech regions from Silero VAD, merged into chunks of at most max_chunk seconds."""
    import torch
    from silero_vad import get_speech_timestamps, load_silero_vad

    model = load_silero_vad()
    spans = get_speech_timestamps(torch.from_numpy(audio), model, sampling_rate=SR,
                                  min_silence_duration_ms=int(min_gap * 1000),
                                  speech_pad_ms=120, return_seconds=True)
    chunks: list[list[float]] = []
    for s in spans:
        if chunks and s["end"] - chunks[-1][0] <= max_chunk and s["start"] - chunks[-1][1] < 1.0:
            chunks[-1][1] = s["end"]
        else:
            chunks.append([s["start"], s["end"]])
    return [(a, b) for a, b in chunks]


class Aligner:
    """MMS_FA forced alignment of arbitrary-script words via uroman."""

    def __init__(self) -> None:
        import torchaudio
        import uroman

        self.bundle = torchaudio.pipelines.MMS_FA
        self.model = self.bundle.get_model()
        self.model.eval()
        self.vocab = self.bundle.get_dict()
        self.tokenizer = self.bundle.get_tokenizer()
        self.aligner = self.bundle.get_aligner()
        self.uroman = uroman.Uroman()

    def romanize(self, word: str) -> str:
        rom = self.uroman.romanize_string(word).lower()
        return "".join(c for c in rom if c in self.vocab and c not in "-*")

    def align(self, audio: np.ndarray, offset: float, words: list[str]) -> list[dict]:
        import torch

        roman = [self.romanize(w) for w in words]
        keep = [i for i, r in enumerate(roman) if r]
        times: dict[int, tuple[float, float]] = {}
        if keep:
            wav = torch.from_numpy(audio).unsqueeze(0)
            with torch.inference_mode():
                emission, _ = self.model(wav)
            ratio = wav.size(1) / emission.size(1) / SR
            try:
                spans = self.aligner(emission[0], self.tokenizer([roman[i] for i in keep]))
                for i, sp in zip(keep, spans):
                    times[i] = (offset + sp[0].start * ratio, offset + sp[-1].end * ratio)
            except RuntimeError as exc:  # text longer than the audio can hold
                print(f"    alignment failed ({exc.__class__.__name__}), spreading words evenly", flush=True)
                return self.spread(words, offset, offset + len(audio) / SR)
        # Words that romanize to nothing (digits, symbols) share the gap around them.
        out = []
        chunk_end = offset + len(audio) / SR
        for i, w in enumerate(words):
            if i in times:
                s, e = times[i]
            else:
                prev_end = out[-1]["end"] if out else offset
                nxt = next((times[j][0] for j in range(i + 1, len(words)) if j in times), chunk_end)
                s, e = prev_end, max(prev_end + 0.05, min(nxt, prev_end + 0.4))
            out.append({"word": w, "start": round(s, 3), "end": round(e, 3)})
        return out


    @staticmethod
    def spread(words: list[str], start: float, end: float) -> list[dict]:
        total = sum(len(w) for w in words) or 1
        out, t = [], start
        for w in words:
            d = (end - start) * len(w) / total
            out.append({"word": w, "start": round(t, 3), "end": round(t + d, 3)})
            t += d
        return out


def leaked_context(text: str, context: str) -> bool:
    """MoulSot sometimes echoes the context prompt on very short chunks."""
    if not context:
        return False
    norm = lambda x: {t.strip(".,;:!?").lower() for t in x.split() if len(t) > 2}  # noqa: E731
    ctx, txt = norm(context), norm(text)
    return bool(txt) and len(txt & ctx) / len(txt) > 0.6


def srt_time(t: float) -> str:
    ms = int(round(t * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def phrases(words: list[dict], max_words: int = 7, gap: float = 0.5) -> list[list[dict]]:
    out: list[list[dict]] = []
    for w in words:
        if out and len(out[-1]) < max_words and w["start"] - out[-1][-1]["end"] < gap:
            out[-1].append(w)
        else:
            out.append([w])
    return out


def write_outputs(video: Path, edit_dir: Path, chunks_text: list[str], words: list[dict]) -> Path:
    ddir = edit_dir / "darija"
    ddir.mkdir(parents=True, exist_ok=True)
    stem = video.stem
    (ddir / f"{stem}.txt").write_text("\n".join(chunks_text) + "\n", encoding="utf-8")
    (ddir / f"{stem}.words.json").write_text(json.dumps(words, ensure_ascii=False, indent=1), encoding="utf-8")
    (ddir / f"{stem}.words.txt").write_text(
        "".join(f"{w['start']:.3f}\t{w['end']:.3f}\t{w['word']}\n" for w in words), encoding="utf-8")
    srt = []
    for n, ph in enumerate(phrases(words), 1):
        srt.append(f"{n}\n{srt_time(ph[0]['start'])} --> {srt_time(ph[-1]['end'])}\n"
                   f"{' '.join(w['word'] for w in ph)}\n")
    (ddir / f"{stem}.srt").write_text("\n".join(srt), encoding="utf-8")

    # Scribe shape for video-use: word + spacing entries.
    scribe: list[dict] = []
    for w in words:
        if scribe and w["start"] > scribe[-1]["end"]:
            scribe.append({"type": "spacing", "text": " ", "start": scribe[-1]["end"],
                           "end": w["start"], "speaker_id": "speaker_0"})
        scribe.append({"type": "word", "text": w["word"], "start": w["start"], "end": w["end"],
                       "speaker_id": "speaker_0"})
    out = edit_dir / "transcripts" / f"{stem}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"language_code": "ary", "engine": "moulsot.v0.3+mms_fa",
                               "text": " ".join(chunks_text), "words": scribe},
                              ensure_ascii=False, indent=1), encoding="utf-8")
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("targets", nargs="+", type=Path)
    ap.add_argument("--context", default="", help="Vocabulary hint passed to MoulSot")
    ap.add_argument("--max-chunk", type=float, default=20.0, help="Max seconds per ASR chunk")
    ap.add_argument("--min-gap", type=float, default=0.3, help="VAD silence that splits speech (s)")
    ap.add_argument("--audio-track", type=int, default=0)
    ap.add_argument("--threads", type=int, default=0, help="torch CPU threads (0 = all)")
    ap.add_argument("--dtype", choices=["bfloat16", "float32"], default="float32",
                    help="Model weights: float32 (default, ~10x faster on CPU) or bfloat16 (half the RAM, very slow on CPU)")
    ap.add_argument("--batch", type=int, default=1, help="ASR chunks per forward pass (memory grows with it)")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    import torch
    from qwen_asr import Qwen3ASRModel

    if args.threads:
        torch.set_num_threads(args.threads)

    asr = aligner = None
    edit_dirs: set[Path] = set()
    for target in args.targets:
        for video in find_sources(target.resolve()):
            edit_dir = edit_dir_for(video)
            edit_dirs.add(edit_dir)
            out = edit_dir / "transcripts" / f"{video.stem}.json"
            if out.exists() and not args.force:
                print(f"cached: {out}")
                continue
            t0 = time.time()
            print(f"{video.name}: VAD", flush=True)
            audio = load_audio(video, args.audio_track)
            chunks = vad_chunks(audio, args.max_chunk, args.min_gap)
            print(f"  {len(chunks)} speech chunks, {sum(b - a for a, b in chunks):.1f}s of speech", flush=True)
            if asr is None:
                print(f"  loading {MODEL_ID} (cpu, {args.dtype})", flush=True)
                asr = Qwen3ASRModel.from_pretrained(MODEL_ID, dtype=getattr(torch, args.dtype), device_map="cpu",
                                                    max_inference_batch_size=args.batch, low_cpu_mem_usage=True)
                aligner = Aligner()
            pieces = [(audio[int(a * SR):int(b * SR)], SR) for a, b in chunks]
            results = asr.transcribe(audio=pieces, context=args.context, language="Arabic")
            for i, res in enumerate(results):
                if leaked_context(res.text or "", args.context):
                    print(f"  chunk {i}: context echoed, retrying without it", flush=True)
                    results[i] = asr.transcribe(audio=pieces[i], language="Arabic")[0]
            chunks_text, words = [], []
            for ci, ((a, b), res) in enumerate(zip(chunks, results)):
                text = (res.text or "").strip()
                chunks_text.append(text)
                if not text:
                    continue
                print(f"  [{a:6.2f}-{b:6.2f}] {text}", flush=True)
                for w in aligner.align(audio[int(a * SR):int(b * SR)], a, text.split()):
                    w["chunk"] = ci
                    words.append(w)
            path = write_outputs(video, edit_dir, chunks_text, words)
            print(f"  {len(words)} words -> {path.name} ({time.time() - t0:.1f}s)", flush=True)

    for edit_dir in sorted(edit_dirs):
        subprocess.run([sys.executable, str(VIDEO_USE_HELPERS / "pack_transcripts.py"),
                        "--edit-dir", str(edit_dir)], check=True)


if __name__ == "__main__":
    main()
