"""Check the studio is ready: tools, packages, video-use, transcription engines."""

from __future__ import annotations

import importlib.util
import os
import shutil
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from studio_paths import VIDEO_USE, VIDEO_USE_HELPERS  # noqa: E402

OK, BAD, WARN = "ok  ", "FAIL", "warn"


def reachable(url: str) -> bool:
    try:
        urllib.request.urlopen(urllib.request.Request(url, method="HEAD"), timeout=8)
        return True
    except urllib.error.HTTPError:
        return True  # host answered
    except Exception:
        return False


def cached_whisper_models() -> list[str]:
    hub = Path(os.environ.get("HF_HOME", Path.home() / ".cache" / "huggingface")) / "hub"
    return sorted(p.name.split("--")[-1] for p in hub.glob("models--*whisper*")) if hub.is_dir() else []


def main() -> int:
    rows: list[tuple[str, str, str]] = []
    for tool in ("ffmpeg", "ffprobe", "node", "npx"):
        rows.append((OK if shutil.which(tool) else (BAD if tool.startswith("ff") else WARN), tool,
                     shutil.which(tool) or "not on PATH"))
    for mod in ("faster_whisper", "scenedetect", "cv2", "librosa", "PIL", "yt_dlp"):
        rows.append((OK if importlib.util.find_spec(mod) else BAD, f"python: {mod}", ""))
    rows.append((OK if (VIDEO_USE_HELPERS / "render.py").exists() else BAD, "video-use", str(VIDEO_USE)))

    models = cached_whisper_models()
    hf = reachable("https://huggingface.co")
    if models:
        rows.append((OK, "transcribe: local", f"cached models: {', '.join(models)}"))
    elif hf:
        rows.append((OK, "transcribe: local", "huggingface.co reachable; first run downloads the model"))
    else:
        rows.append((BAD, "transcribe: local",
                     "huggingface.co blocked and no cached model. Allow huggingface.co and "
                     "*.hf.co in the environment's network settings"))

    key = os.environ.get("ELEVENLABS_API_KEY") or (VIDEO_USE / ".env").exists()
    el = reachable("https://api.elevenlabs.io")
    rows.append((OK if key and el else WARN, "transcribe: scribe",
                 ("key set" if key else "no ELEVENLABS_API_KEY") + ", " +
                 ("api.elevenlabs.io reachable" if el else "api.elevenlabs.io blocked")))

    for status, name, note in rows:
        print(f"[{status}] {name:22} {note}")
    return 1 if any(r[0] == BAD for r in rows) else 0


if __name__ == "__main__":
    sys.exit(main())
