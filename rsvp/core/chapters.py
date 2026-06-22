"""Detect chapter/section headings in plain text and map them to word indices.

Plain ``.txt`` has no real structure, so this is a conservative heuristic: lines
that look like headings (``Chapter 4``, ``PART II``, a Markdown ``# Title``,
``Prologue``…). Each heading is mapped to the index of its first word, so a host
can offer a "jump to chapter" list. When nothing is found the host can fall back
to plain progress markers.

UI-agnostic; works from the raw text plus the word start-offsets (``token_spans``
starts), so it stays in sync with how the engine tokenized the book.
"""

from __future__ import annotations

import bisect
import re

# A heading is a whole line that is one of:
#   * a Markdown heading (#..###### Title)
#   * Chapter/Part/Book/Canto/Section followed by a number or roman numeral
#   * a standalone front/back-matter word (Prologue, Epilogue, Preface, …)
_HEADING_RE = re.compile(
    r"^[ \t]*("
    r"#{1,6}[ \t]+\S.*"
    r"|(?:chapter|part|book|canto|section)[ \t]+[0-9ivxlcdm]+\b.*"
    r"|(?:prologue|epilogue|introduction|preface|foreword|afterword)\b.*"
    r")[ \t]*$",
    re.IGNORECASE | re.MULTILINE,
)


def _clean_title(line: str) -> str:
    title = re.sub(r"\s+", " ", line.strip().lstrip("#").strip())
    return title[:42]


def find_chapters(text: str, span_starts: list[int]) -> list[tuple[str, int]]:
    """Return ``(title, word_index)`` for each detected heading, in order.

    ``span_starts`` is the list of word start offsets (``s`` from
    ``token_spans``). Returns an empty list when no headings are found.
    """
    if not span_starts:
        return []
    chapters: list[tuple[str, int]] = []
    last_wi = -1
    for m in _HEADING_RE.finditer(text):
        title = _clean_title(m.group(0))
        if not title:
            continue
        wi = bisect.bisect_left(span_starts, m.start())
        wi = min(wi, len(span_starts) - 1)
        if wi == last_wi:
            continue
        chapters.append((title, wi))
        last_wi = wi
    return chapters
