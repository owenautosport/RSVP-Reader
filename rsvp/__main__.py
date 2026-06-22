"""Run the reader:  python3 -m rsvp [BOOK.txt]

With no argument it opens the bundled sample book so there is always something
to read. Press  o  inside the app to open one of your own.
"""

from __future__ import annotations

import sys
from pathlib import Path

from .ui import run

_SAMPLE = Path(__file__).resolve().parent.parent / "samples" / "sample.txt"


def main() -> None:
    if len(sys.argv) > 1:
        book = Path(sys.argv[1])
    else:
        book = _SAMPLE if _SAMPLE.is_file() else None
    run(book)


if __name__ == "__main__":
    main()
