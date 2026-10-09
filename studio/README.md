# Studio

Claude's video editing toolkit. The editor playbook is in `/CLAUDE.md`.

```bash
bash studio/setup.sh                        # once per session
PY=studio/.venv/bin/python
$PY studio/bin/new_project.py acme launch ~/footage/*.mp4
$PY studio/bin/analyze.py projects/acme/launch
$PY studio/bin/transcribe.py projects/acme/launch --language en
# ... Claude writes edit/edl.json, renders with video-use, you review ...
$PY studio/bin/export.py projects/acme/launch/edit/final.mp4 reels youtube
```

| Script | Does |
|---|---|
| `setup.sh` | venv, Python deps, clones browser-use/video-use into `.vendor/`, runs doctor |
| `bin/doctor.py` | Checks tools, packages and which transcription engines can run |
| `bin/new_project.py` | Creates `projects/<client>/<project>/` and ingests files or URLs |
| `bin/analyze.py` | Metadata, scene cuts, labelled contact sheets, loudness, silences |
| `bin/transcribe.py` | Word-level transcripts (faster-whisper locally, or ElevenLabs Scribe) |
| `bin/export.py` | Platform masters: reframe, captions, -14 LUFS, H.264, poster frame |
| `bin/enhance_photo.py` | Cover photos: Real-ESRGAN x4 upscale (Darija venv), HDR look (`--lift`, `--clarity`) |
| `bin/retouch_teeth.py` | Natural teeth retouch: whiten, clean stains, fill dark gaps (`--roi`, `--gaps`, `--row`) |
| `bin/render_cover.py` | HTML cover page to PNG/JPG, at 2x (2160x3840) + a 1080 copy |

Cutting, grading, overlays and subtitles come from video-use's helpers
(`render.py`, `grade.py`, `timeline_view.py`, `pack_transcripts.py`).

## Models (subject tracking)

`studio/.models/` is gitignored; fetch once per container:

```bash
mkdir -p studio/.models && cd studio/.models
curl -sSLo yunet.onnx https://huggingface.co/opencv/face_detection_yunet/resolve/main/face_detection_yunet_2023mar.onnx   # MIT
curl -sSLo modnet.onnx https://huggingface.co/Xenova/modnet/resolve/main/onnx/model.onnx                                # Apache-2.0
curl -sSLo RealESRGAN_x4plus.pth https://github.com/xinntao/Real-ESRGAN/releases/download/v0.1.0/RealESRGAN_x4plus.pth  # BSD-3, studio/bin/enhance_photo.py
```

## Network requirements

- Local transcription downloads Whisper models from `huggingface.co` (files are
  served from `*.hf.co`) the first time each model is used.
- Scribe needs `api.elevenlabs.io` and `ELEVENLABS_API_KEY`.
- URL ingest with yt-dlp needs the video host allowed.
