"""What every render script takes: an output folder and a window size.

    .venv/bin/python scripts/render_<x>.py [output dir] [--size WIDTHxHEIGHT] [--lang CODE]

The default size is 1366x768 (ADR 0002's design size); 1920x1080 is the
check size. Without a folder, the renders go to
docs/design/ui-refresh/renders/final/<size>/. --lang renders the app's
strings in that language (en by default, bg for the Bulgarian renders).
"""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from shared.i18n import LANGUAGES

FINAL = ROOT / "docs" / "design" / "ui-refresh" / "renders" / "final"


def _size(text: str) -> tuple[int, int]:
    try:
        width, height = (int(part) for part in text.lower().split("x"))
    except ValueError:
        raise argparse.ArgumentTypeError(f"{text!r} is not WIDTHxHEIGHT") from None
    if width <= 0 or height <= 0:
        raise argparse.ArgumentTypeError(f"{text!r} is not WIDTHxHEIGHT")
    return width, height


def parse_args(argv: list[str]) -> tuple[Path, int, int, str]:
    parser = argparse.ArgumentParser(description="Render frames offscreen.")
    parser.add_argument("out", nargs="?", type=Path, default=None)
    parser.add_argument("--size", type=_size, default=(1366, 768), metavar="WIDTHxHEIGHT")
    parser.add_argument("--lang", default="en", choices=sorted(LANGUAGES))
    args = parser.parse_args(argv)
    width, height = args.size
    return args.out or FINAL / f"{width}x{height}", width, height, args.lang
