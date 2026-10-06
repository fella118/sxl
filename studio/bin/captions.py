"""Build the output-timeline SRT for an EDL without rendering.

Uses video-use's own builder, so timing matches `render.py --build-subtitles`.
Use it for vertical deliverables (render the master with --no-subtitles, then
`export.py ... --subs`) and for sidecar caption files clients upload to
YouTube/LinkedIn.

Usage:
    python studio/bin/captions.py projects/acme/launch/edit/edl.json
    python studio/bin/captions.py edit/edl.json -o deliver/launch_en.srt
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from studio_paths import VIDEO_USE_HELPERS  # noqa: E402

sys.path.insert(0, str(VIDEO_USE_HELPERS))
from render import build_master_srt  # noqa: E402  (video-use)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("edl", type=Path)
    ap.add_argument("-o", "--output", type=Path, default=None, help="Default: <edit>/master.srt")
    args = ap.parse_args()

    edl_path = args.edl.resolve()
    out = (args.output or edl_path.parent / "master.srt").resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    build_master_srt(json.loads(edl_path.read_text()), edl_path.parent, out)
    print(out)


if __name__ == "__main__":
    main()
