"""Run the reader:  python3 -m rsvp [BOOK]

With no argument it opens the bundled sample (the onboarding guide) so there is
always something to read. Inside the app, use the Library to add your own books.
"""

from __future__ import annotations

import sys
from pathlib import Path

from .ui import run
from .ui.app import _SAMPLES_DIR

_SAMPLE = _SAMPLES_DIR / "sample.txt"


def main() -> None:
    if len(sys.argv) > 1:
        book = Path(sys.argv[1])
    else:
        book = _SAMPLE if _SAMPLE.is_file() else None
    run(book)


if __name__ == "__main__":
    main()
