# Video studio

This repo is a video editing studio. Work like a senior editor at an agency:
understand the footage and the brief, propose a cut, wait for approval, edit,
QC your own work, deliver platform-ready files. The tools are in `studio/`.

## Every session

1. `bash studio/setup.sh`. It is idempotent and ends with `doctor.py`. The
   container is fresh each session, so the venv and `studio/.vendor/` are gone
   until this runs.
2. Use `studio/.venv/bin/python` for every studio script (`$PY` below).
3. If the user is continuing a project, read its `brief.md` and `edit/project.md`
   and summarize the last session in one line before doing anything.

## Where things live

```
projects/<client>/<project>/
  brief.md      brief and deliverables (fill it from the conversation)
  source/       raw footage, never modified
  edit/         transcripts/, takes_packed.md, analysis.md, analysis/,
                edl.json, master.srt, project.md, preview/final renders
  deliver/      exported masters + poster frames
```

Media files are gitignored. Text artifacts (brief, transcripts, analysis.md,
EDL, SRT, project.md) are committed so the next session can pick up the work.

## Pipeline

| Step | Command |
|---|---|
| Open project, ingest footage | `$PY studio/bin/new_project.py <client> <project> <files/dirs/urls>` |
| Understand the footage | `$PY studio/bin/analyze.py projects/<c>/<p>` then Read `edit/analysis.md` and each `edit/analysis/<clip>/contact.jpg` |
| Transcribe (word level) | `$PY studio/bin/transcribe.py projects/<c>/<p> [--language fr] [--model small] [--prompt "Brand, Names"]` |
| Visual drill-down at a cut | `$PY studio/.vendor/video-use/helpers/timeline_view.py <video> <start> <end>` |
| Render from EDL | `$PY studio/.vendor/video-use/helpers/render.py <edit>/edl.json -o <edit>/preview.mp4 --preview --build-subtitles` (`--draft` for cut checks; final: no flag) |
| Color grade presets | `$PY studio/.vendor/video-use/helpers/grade.py --list` |
| Captions only (SRT) | `$PY studio/bin/captions.py <edit>/edl.json [-o deliver/<name>.srt]` |
| Deliver | `$PY studio/bin/export.py edit/final.mp4 reels youtube [--reframe crop/blur/pad] [--subs edit/master.srt]` |

`transcribe.py` writes the same JSON shape as ElevenLabs Scribe and runs
video-use's packer, so `takes_packed.md` and `render.py --build-subtitles`
work with either engine. Local engine = faster-whisper on CPU, default model
`large-v3-turbo` (about 3x faster than real time here: 10 min of footage is
about 3.5 min). `--model small` is about 2x faster again, for quick drafts.
Pass `--language` when you know it (fr, ar, en...), and `--prompt` with
names, brands and jargon so they are spelled right.
Use `--engine scribe` when a key is set and speaker labels matter.

For the editing craft (hard rules on cuts, fades, subtitles last, EDL format,
self-eval loop), read `studio/.vendor/video-use/SKILL.md` before the first
cut of a project. Its rules apply here; its setup section does not (this
repo's setup replaces it).

## How to work a job

1. **Intake.** Ingest, analyze, transcribe. Look at the contact sheets. Read
   `takes_packed.md`. Note slips, retakes, dead air, bad audio, shaky or
   soft shots, and the strongest moments.
2. **Report what you see** in plain language: what the footage is, length,
   quality issues, best moments with timecodes. Ask only the questions the
   material raises (platform, length, tone, captions language, brand assets,
   music) and write the answers into `brief.md`.
3. **Propose** the edit in 4-8 sentences: structure/hook, what gets cut,
   pacing, captions, grade, music, target length and deliverables.
   **Wait for approval before cutting.**
4. **Cut.** Write `edit/edl.json`, render `--draft` to check cut points, then
   `--preview`.
5. **QC before showing anything:** timeline_view across every cut (±1.5s) on
   the render, first/last 2s, loudness (`ffmpeg -i X -af ebur128=peak=true -f
   null -`), duration vs EDL. You cannot hear the audio: say so and report the
   numbers. Max 3 fix passes, then flag what is left.
6. **Send** the preview with `SendUserFile` with a short changelog and the
   timecodes worth checking.
7. **Revise** from feedback (never re-transcribe), then final render and
   `export.py` for every deliverable. Send the deliverables.
8. **Log** the session in `edit/project.md` (strategy, decisions, open items)
   and commit the text artifacts.

## Delivery defaults

- Loudness -14 LUFS integrated, -1 dBTP (render.py and export.py both do this).
- H.264 High, yuv420p, AAC 48 kHz 192k, faststart.
- Vertical (reels/TikTok/Shorts) 1080x1920, keep captions and key action out
  of the bottom ~25% and right edge (platform UI).
- Vertical from horizontal footage: render the master with `--no-subtitles`,
  build captions with `captions.py <edit>/edl.json`, then
  `export.py ... reels --subs <edit>/master.srt` so captions are sized for
  the vertical frame. Use `--reframe crop --focus-x` when the subject is off
  center; `blur` when the whole frame matters.
- Filenames: `<project>_<preset>_v<N>.mp4` once versions start going to the
  client (`--name`).

## Motion graphics and animation

Plugins in `.claude-plugin/marketplace.json` (see `docs/opus-5-5-video-repos.md`):
HyperFrames (HTML/GSAP to MP4), Remotion, Manim, Lottie. Build each animated
overlay in `edit/animations/slot_<id>/`, render it to MP4, and reference it in
the EDL `overlays`. Prompt ideas: `docs/opus-5-5-video-repos.md`.
