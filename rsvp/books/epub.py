"""Parse an EPUB into plain text plus chapter offsets — standard library only.

An EPUB is a ZIP containing XHTML documents, a package file (``.opf``) that
lists them and gives their reading order (the "spine"), and some metadata. We
read the spine in order, strip each XHTML document to text, and record where
each document (chapter) starts so the reader can offer a real chapter list.

No third-party dependencies: ``zipfile`` + ``xml.etree`` + ``html.parser``. This
keeps the reader fully offline and dependency-free.
"""

from __future__ import annotations

import posixpath
import re
import zipfile
from html.parser import HTMLParser
from urllib.parse import unquote
from xml.etree import ElementTree as ET

# Tags whose content we never want as reading text.
_SKIP_TAGS = {"script", "style", "head", "title"}
# Block-level tags: their boundaries become paragraph breaks.
_BLOCK_TAGS = {
    "p", "div", "br", "li", "tr", "blockquote", "section", "article",
    "h1", "h2", "h3", "h4", "h5", "h6", "header", "footer", "figcaption",
}
_HEADINGS = {"h1", "h2", "h3", "h4", "h5", "h6"}


def _localname(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


class _HtmlText(HTMLParser):
    """Collect readable text and the first heading from one XHTML document."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._parts: list[str] = []
        self._skip = 0
        self._heading_depth = 0
        self._heading_buf: list[str] = []
        self.first_heading: str | None = None

    def handle_starttag(self, tag, attrs):
        if tag in _SKIP_TAGS:
            self._skip += 1
        if tag in _BLOCK_TAGS:
            self._parts.append("\n")
        if tag in _HEADINGS:
            self._heading_depth += 1

    def handle_endtag(self, tag):
        if tag in _SKIP_TAGS and self._skip:
            self._skip -= 1
        if tag in _BLOCK_TAGS:
            self._parts.append("\n")
        if tag in _HEADINGS and self._heading_depth:
            self._heading_depth -= 1
            if self.first_heading is None:
                heading = " ".join("".join(self._heading_buf).split())
                if heading:
                    self.first_heading = heading[:60]

    def handle_data(self, data):
        if self._skip:
            return
        self._parts.append(data)
        if self._heading_depth:
            self._heading_buf.append(data)

    def get_text(self) -> str:
        text = "".join(self._parts)
        text = re.sub(r"[ \t\r\f\v]+", " ", text)
        text = re.sub(r" *\n *", "\n", text)
        text = re.sub(r"\n{2,}", "\n\n", text)
        return text.strip()


def _find_opf_path(z: zipfile.ZipFile) -> str:
    data = z.read("META-INF/container.xml")
    root = ET.fromstring(data)
    for el in root.iter():
        if _localname(el.tag) == "rootfile" and el.get("full-path"):
            return el.get("full-path")
    raise ValueError("EPUB container has no rootfile")


def _parse_opf(z: zipfile.ZipFile, opf_path: str) -> tuple[dict[str, str], list[str]]:
    root = ET.fromstring(z.read(opf_path))
    manifest: dict[str, str] = {}
    spine: list[str] = []
    for el in root.iter():
        name = _localname(el.tag)
        if name == "item" and el.get("id") and el.get("href"):
            manifest[el.get("id")] = unquote(el.get("href"))
        elif name == "itemref" and el.get("idref"):
            spine.append(el.get("idref"))
    return manifest, spine


def epub_title(path) -> str | None:
    """The book's title from its OPF metadata (``dc:title``), or None."""
    try:
        with zipfile.ZipFile(path) as z:
            root = ET.fromstring(z.read(_find_opf_path(z)))
        for el in root.iter():
            if _localname(el.tag) == "title" and (el.text or "").strip():
                return el.text.strip()
    except Exception:
        return None
    return None


def parse_epub(path) -> tuple[str, list[tuple[str, int]]]:
    """Return ``(text, chapters)`` where chapters is ``[(title, char_offset)]``."""
    with zipfile.ZipFile(path) as z:
        names = set(z.namelist())
        opf_path = _find_opf_path(z)
        opf_dir = posixpath.dirname(opf_path)
        manifest, spine = _parse_opf(z, opf_path)

        text = ""
        chapters: list[tuple[str, int]] = []
        for idref in spine:
            href = manifest.get(idref)
            if not href:
                continue
            doc_path = posixpath.normpath(posixpath.join(opf_dir, href))
            if doc_path not in names:
                continue
            parser = _HtmlText()
            parser.feed(z.read(doc_path).decode("utf-8", "replace"))
            doc_text = parser.get_text()
            if not doc_text:
                continue
            if text:
                text += "\n\n"
            start = len(text)
            if parser.first_heading:
                chapters.append((parser.first_heading, start))
            text += doc_text
    return text, chapters
