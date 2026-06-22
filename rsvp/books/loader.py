"""Read a book file from local storage into plain text.

Only ``.txt`` is handled for now. The function dispatches on file extension so
adding a parser (e.g. EPUB or PDF) later means adding one branch here and
nothing else changes elsewhere in the app.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

SUPPORTED_EXTENSIONS = (".txt",)


def find_books(directories: Iterable[str | Path]) -> list[Path]:
    """Return supported book files found across ``directories``.

    Non-recursive, de-duplicated by resolved path, sorted by display name. Used
    by the Library screen to list what's available on local storage.
    """
    seen: dict[Path, Path] = {}
    for directory in directories:
        d = Path(directory)
        if not d.is_dir():
            continue
        for entry in d.iterdir():
            if entry.is_file() and entry.suffix.lower() in SUPPORTED_EXTENSIONS:
                seen.setdefault(entry.resolve(), entry)
    return sorted(seen.values(), key=lambda p: p.stem.lower())


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
