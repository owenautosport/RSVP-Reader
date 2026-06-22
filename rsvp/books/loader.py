"""Read a book file from local storage into plain text (+ chapter structure).

Dispatches on file extension so adding a format (EPUB now; PDF later) means
adding one branch here and nothing else changes elsewhere in the app. Plain text
formats have no inherent chapter structure; EPUB does, so the loader can return
chapter offsets alongside the text.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

from .epub import parse_epub
from .pdf import parse_pdf, PdfSupportMissing

SUPPORTED_EXTENSIONS = (".txt", ".epub", ".pdf")


@dataclass
class LoadedBook:
    text: str
    # (chapter title, character offset into text); empty when the format has no
    # inherent structure (the host then falls back to heading detection).
    chapters: list[tuple[str, int]] = field(default_factory=list)


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


def load_book_full(path: str | Path) -> LoadedBook:
    """Load a book as text plus any chapter offsets.

    Raises ``BookLoadError`` for a missing file or an unsupported format.
    """
    path = Path(path)
    if not path.is_file():
        raise BookLoadError(f"No such book file: {path}")

    suffix = path.suffix.lower()
    if suffix == ".txt":
        return LoadedBook(_load_txt(path))
    if suffix == ".epub":
        try:
            text, chapters = parse_epub(path)
        except Exception as exc:  # malformed EPUB -> friendly error
            raise BookLoadError(f"Couldn't read EPUB: {exc}") from exc
        if not text.strip():
            raise BookLoadError("EPUB contained no readable text")
        return LoadedBook(text, chapters)
    if suffix == ".pdf":
        try:
            text, chapters = parse_pdf(path)
        except PdfSupportMissing as exc:
            raise BookLoadError(str(exc)) from exc
        except Exception as exc:
            raise BookLoadError(f"Couldn't read PDF: {exc}") from exc
        if not text.strip():
            raise BookLoadError("No selectable text in this PDF (scanned images?)")
        return LoadedBook(text, chapters)

    raise BookLoadError(
        f"Unsupported format '{suffix or '(none)'}'. "
        f"Supported: {', '.join(SUPPORTED_EXTENSIONS)}"
    )


def load_book(path: str | Path) -> str:
    """Return just the plain-text content of the book at ``path``."""
    return load_book_full(path).text


def _load_txt(path: Path) -> str:
    # utf-8 with a forgiving fallback so an odd byte never crashes the reader.
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="utf-8", errors="replace")
