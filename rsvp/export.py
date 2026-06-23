"""Export a book to the pocket device's simple ``.rsvp`` format.

The device can't parse EPUB/PDF, so the desktop app does it once and writes a
plain file the firmware just reads. We reuse the existing parsers + chapter
detection, so the device gets ready-made text and chapter jump points.

Format (UTF-8)::

    RSVP1
    T\t<title>
    C\t<word-index>\t<chapter title>      (zero or more)
    B
    <the whole book text…>

The header is line-based up to the ``B`` marker; everything after it is the
verbatim text (so blank lines / a stray "B" inside the book are harmless). Word
indices match whitespace tokenization of that text — the same the device uses.
"""

from __future__ import annotations

import bisect
import re
import sys
from pathlib import Path

from .books import book_title, load_book_full
from .core import find_chapters, token_spans

MAGIC = "RSVP1"


def _field(s: str) -> str:
    return s.replace("\t", " ").replace("\n", " ").strip()


def _safe_name(s: str) -> str:
    return re.sub(r"[^\w.-]+", "_", s).strip("_") or "book"


def _chapters_as_word_indices(book, span_starts: list[int]) -> list[tuple[int, str]]:
    """Return (word-index, title), from EPUB/PDF char offsets or the txt heuristic."""
    if book.chapters:  # (title, char-offset) from the parser
        out = []
        for title, offset in book.chapters:
            wi = min(bisect.bisect_left(span_starts, offset),
                     max(0, len(span_starts) - 1))
            out.append((wi, title))
        return out
    return [(wi, title) for title, wi in find_chapters(book.text, span_starts)]


def export_book(src_path, dest_dir, title: str | None = None) -> Path:
    """Write ``<title>.rsvp`` for the book at ``src_path`` into ``dest_dir``."""
    src = Path(src_path)
    dest_dir = Path(dest_dir)
    book = load_book_full(src)
    starts = [s for s, _ in token_spans(book.text)]
    chapters = _chapters_as_word_indices(book, starts)
    name = title or book_title(src)

    lines = [MAGIC, f"T\t{_field(name)}"]
    for wi, ct in chapters:
        lines.append(f"C\t{wi}\t{_field(ct)}")
    lines.append("B")

    dest_dir.mkdir(parents=True, exist_ok=True)
    out = dest_dir / (_safe_name(name) + ".rsvp")
    out.write_text("\n".join(lines) + "\n" + book.text, encoding="utf-8")
    return out


def _cli() -> None:
    if len(sys.argv) < 3:
        print("usage: python -m rsvp.export <book> <dest-dir>")
        raise SystemExit(2)
    print("wrote", export_book(sys.argv[1], sys.argv[2]))


if __name__ == "__main__":
    _cli()
