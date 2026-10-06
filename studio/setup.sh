#!/usr/bin/env bash
# Idempotent setup for the video studio. Safe to re-run every session.
#   bash studio/setup.sh
set -euo pipefail

STUDIO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$STUDIO/.venv"
VIDEO_USE="$STUDIO/.vendor/video-use"

need() { command -v "$1" >/dev/null || { echo "missing: $1 ($2)"; exit 1; }; }
need ffmpeg  "apt-get install -y ffmpeg"
need ffprobe "apt-get install -y ffmpeg"
need git     "apt-get install -y git"

# video-use: the EDL renderer, grader, timeline viewer and transcript packer.
if [ -d "$VIDEO_USE/.git" ]; then
  git -C "$VIDEO_USE" pull -q --ff-only || echo "video-use: pull failed, keeping current checkout"
else
  mkdir -p "$(dirname "$VIDEO_USE")"
  git clone -q --depth 1 https://github.com/browser-use/video-use "$VIDEO_USE"
fi

if command -v uv >/dev/null; then
  [ -x "$VENV/bin/python" ] || uv venv -q "$VENV"
  uv pip install -q --python "$VENV/bin/python" -r "$STUDIO/requirements.txt"
else
  [ -x "$VENV/bin/python" ] || python3 -m venv "$VENV"
  "$VENV/bin/pip" install -q -r "$STUDIO/requirements.txt"
fi

# Darija pipeline: Silero VAD -> MoulSot v0.3 -> MMS alignment (own venv).
DVENV="$STUDIO/.venv-darija"
if command -v uv >/dev/null; then
  [ -x "$DVENV/bin/python" ] || uv venv -q "$DVENV" --python 3.12
  uv pip install -q --python "$DVENV/bin/python" torch torchaudio --index-url https://download.pytorch.org/whl/cpu
  uv pip install -q --python "$DVENV/bin/python" -r "$STUDIO/requirements-darija.txt"
fi

echo "studio ready"
echo "  python:    $VENV/bin/python"
echo "  darija:    $DVENV/bin/python studio/bin/darija_transcribe.py"
echo "  video-use: $VIDEO_USE/helpers"
"$VENV/bin/python" "$STUDIO/bin/doctor.py" || true
