"""Shared paths and project layout for the studio scripts.

    projects/<client>/<project>/
        brief.md       client brief and deliverables
        source/        raw footage, untouched (gitignored media)
        edit/          video-use edit dir: transcripts, takes_packed.md,
                       analysis.md, edl.json, project.md, master.srt, renders
        deliver/       exported masters per platform (gitignored media)
"""

from __future__ import annotations

from pathlib import Path

STUDIO = Path(__file__).resolve().parent.parent
REPO = STUDIO.parent
PROJECTS = REPO / "projects"
VIDEO_USE = STUDIO / ".vendor" / "video-use"
VIDEO_USE_HELPERS = VIDEO_USE / "helpers"

VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".m4v", ".avi", ".webm", ".mts", ".m2ts", ".mxf", ".3gp"}
AUDIO_EXTS = {".wav", ".mp3", ".m4a", ".aac", ".flac", ".ogg", ".opus"}
MEDIA_EXTS = VIDEO_EXTS | AUDIO_EXTS


def project_dir_for(path: Path) -> Path:
    """The project a source file or project subfolder belongs to."""
    path = path.resolve()
    if path.is_file():
        path = path.parent
    if path.name == "proxy" and path.parent.name == "edit":
        return path.parent.parent
    if path.name in {"source", "edit", "deliver"}:
        return path.parent
    return path


def edit_dir_for(video: Path) -> Path:
    return project_dir_for(video) / "edit"


def find_sources(target: Path) -> list[Path]:
    """A media file, or every media file in a project's source/ (or the dir itself)."""
    target = target.resolve()
    if target.is_file():
        return [target]
    folder = target / "source" if (target / "source").is_dir() else target
    files = sorted(p for p in folder.iterdir()
                   if p.is_file() and p.suffix.lower() in MEDIA_EXTS)
    if not files:
        raise SystemExit(f"no media files in {folder}")
    return files
