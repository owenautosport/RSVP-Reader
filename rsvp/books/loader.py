"""Read a book file from local storage into plain text.

Only ``.txt`` is handled for now. The function dispatches on file extension so
adding a parser (e.g. EPUB or PDF) later means adding one branch here and
nothing else changes elsewhere in the app.
"""

from __future__ import annotations

from pathlib import Path

SUPPORTED_EXTENSIONS = (".txt",)


class BookLoadError(Exception):
    """Raised when a book cannot be read or its format is unsupported."""


def load_book(path: str | Path) -> str:
    """Return the plain-text content of the book at ``path``.

    Raises ``BookLoadError`` for a missing file or an unsupported format.
    """
    path = Path(path)
    if not path.is_file():
        raise BookLoadError(f"No such book file: {path}")

    suffix = path.suffix.lower()
    if suffix == ".txt":
        return _load_txt(path)

    raise BookLoadError(
        f"Unsupported format '{suffix or '(none)'}'. "
        f"Supported: {', '.join(SUPPORTED_EXTENSIONS)}"
    )


def _load_txt(path: Path) -> str:
    # utf-8 with a forgiving fallback so an odd byte never crashes the reader.
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="utf-8", errors="replace")
