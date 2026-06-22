"""Parse a PDF into plain text plus chapter offsets.

PDF text extraction genuinely needs a parser, so this is the one format that
relies on a third-party package: ``pypdf`` (pure Python, MIT, works fully
offline once installed). It is imported lazily, so the rest of the reader — and
``.txt`` / ``.epub`` — stay dependency-free and keep working without it.

Chapters come from the PDF's outline (bookmarks) when present, mapped to the
character offset of the page they point at; otherwise the host falls back to
heading detection / progress markers like any plain text.
"""

from __future__ import annotations

import re


class PdfSupportMissing(RuntimeError):
    """Raised when pypdf isn't installed."""


def _reader_class():
    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover - depends on environment
        raise PdfSupportMissing(
            "PDF support needs the 'pypdf' package (pip install pypdf)"
        ) from exc
    return PdfReader


def _normalize(text: str) -> str:
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\n{2,}", "\n\n", text)
    return text.strip()


def pdf_title(path) -> str | None:
    """The PDF's document title from its metadata, or None (incl. no pypdf)."""
    try:
        reader = _reader_class()(str(path))
        meta = reader.metadata
        title = meta.title if meta else None
        return title.strip() if title and title.strip() else None
    except Exception:
        return None


def parse_pdf(path) -> tuple[str, list[tuple[str, int]]]:
    """Return ``(text, chapters)`` where chapters is ``[(title, char_offset)]``."""
    reader = _reader_class()(str(path))

    text = ""
    page_offsets: list[int] = []
    for page in reader.pages:
        try:
            page_text = _normalize(page.extract_text() or "")
        except Exception:
            page_text = ""
        if text and page_text:
            text += "\n\n"
        page_offsets.append(len(text))  # where this page begins in the text
        text += page_text

    chapters = _outline_chapters(reader, page_offsets)
    return text.strip(), chapters


def _outline_chapters(reader, page_offsets: list[int]) -> list[tuple[str, int]]:
    try:
        outline = reader.outline
    except Exception:
        return []

    chapters: list[tuple[str, int]] = []

    def walk(items):
        for item in items:
            if isinstance(item, list):
                walk(item)
                continue
            title = getattr(item, "title", None)
            try:
                page_no = reader.get_destination_page_number(item)
            except Exception:
                page_no = None
            if title and page_no is not None and 0 <= page_no < len(page_offsets):
                chapters.append((str(title).strip()[:60], page_offsets[page_no]))

    try:
        walk(outline)
    except Exception:
        return []
    chapters.sort(key=lambda c: c[1])
    return chapters
