"""Create a client project and bring footage into it.

Sources can be local files/folders (copied, or moved with --move) or URLs
(downloaded with yt-dlp). The originals are never modified.

Usage:
    python studio/bin/new_project.py <client> <project> [sources...]
    python studio/bin/new_project.py acme spring-launch ~/uploads/*.mp4
    python studio/bin/new_project.py acme spring-launch https://example.com/raw.mp4
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from studio_paths import MEDIA_EXTS, PROJECTS  # noqa: E402

BRIEF = """# {client} / {project}

Opened {today}.

## Brief
- Goal / message:
- Audience and platform:
- Deliverables (format, aspect, length):
- Tone and references:
- Brand: fonts, colors, logo, lower-thirds, music rules
- Must keep:
- Must cut:
- Captions: language, style
- Deadline:

## Sources
{sources}
"""


def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-") or "untitled"


def ingest(src: str, dest: Path, move: bool) -> list[Path]:
    if re.match(r"https?://", src):
        subprocess.run(["yt-dlp", "-q", "-o", str(dest / "%(title).80s.%(ext)s"),
                        "-f", "bv*+ba/b", "--merge-output-format", "mp4", src], check=True)
        return sorted(dest.iterdir())
    path = Path(src).expanduser()
    files = [path] if path.is_file() else sorted(p for p in path.rglob("*") if p.suffix.lower() in MEDIA_EXTS)
    out = []
    for f in files:
        target = dest / f.name
        if target.exists():
            print(f"  exists, skipped: {target.name}")
            continue
        (shutil.move if move else shutil.copy2)(f, target)
        out.append(target)
        print(f"  {'moved' if move else 'copied'}: {f.name}")
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("client")
    ap.add_argument("project")
    ap.add_argument("sources", nargs="*")
    ap.add_argument("--move", action="store_true", help="Move local files instead of copying")
    args = ap.parse_args()

    root = PROJECTS / slug(args.client) / slug(args.project)
    for sub in ("source", "edit", "deliver"):
        (root / sub).mkdir(parents=True, exist_ok=True)

    for src in args.sources:
        ingest(src, root / "source", args.move)

    brief = root / "brief.md"
    listing = "\n".join(f"- {p.name}" for p in sorted((root / "source").iterdir())) or "- (none yet)"
    if not brief.exists():
        brief.write_text(BRIEF.format(client=args.client, project=args.project,
                                      today=date.today().isoformat(), sources=listing))
    print(root)


if __name__ == "__main__":
    main()
