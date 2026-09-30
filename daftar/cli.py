"""Command line: `daftar demo` starts the browser demo."""

import argparse
from pathlib import Path

from .server import serve


def main() -> None:
    parser = argparse.ArgumentParser(prog="daftar", description="Daftar: document collection assistant for fiduciaires")
    sub = parser.add_subparsers(dest="command", required=True)
    demo = sub.add_parser("demo", help="start the browser demo (simulated WhatsApp + owner dashboard)")
    demo.add_argument("--port", type=int, default=8000)
    demo.add_argument("--host", default="127.0.0.1")
    demo.add_argument("--data", default="demo-data", help="folder for the demo database and received files")
    args = parser.parse_args()

    data = Path(args.data)
    data.mkdir(parents=True, exist_ok=True)
    serve(data / "daftar.db", data / "files", host=args.host, port=args.port)


if __name__ == "__main__":
    main()
