"""Turn raw book text into the sequence of words shown one-at-a-time.

Kept deliberately small and dependency-free. The only rule for now is "split on
whitespace", which is correct for the plain-text books the MVP loads. Smarter
handling (very long words, hyphenation, numbers) can grow here later without the
engine or UI needing to change.
"""

from __future__ import annotations

import re

_WORD_RE = re.compile(r"\S+")


def token_spans(text: str) -> list[tuple[int, int]]:
    """Return the ``(start, end)`` character span of every word in ``text``.

    Whitespace separates words but is not included in any span. The list lines
    up one-to-one with :func:`tokenize`, so word ``i`` occupies ``spans[i]`` in
    the original text. A host can use this to map a position in the full text
    back to a word index (e.g. to highlight or jump to the current word in a
    "read normally" view).
    """
    return [m.span() for m in _WORD_RE.finditer(text)]


def paragraph_end_indices(text: str) -> set[int]:
    """Return the indices of words that fall at the end of a paragraph.

    A paragraph break is detected as a blank line (two or more newlines) in the
    whitespace separating two words. Lines merely wrapped with a single newline
    inside a paragraph are not counted. Indices line up with :func:`tokenize`,
    so a host/engine can add an extra pause after those words.
    """
    spans = token_spans(text)
    ends: set[int] = set()
    for i in range(len(spans) - 1):
        gap = text[spans[i][1]:spans[i + 1][0]]
        if gap.count("\n") >= 2:
            ends.add(i)
    return ends


def tokenize(text: str) -> list[str]:
    """Split ``text`` into a flat list of display words.

    Whitespace (spaces, tabs, newlines) is collapsed and used purely as a
    separator, so paragraph breaks do not produce empty tokens. The original
    punctuation attached to each word is preserved, because the engine uses it
    to decide how long to linger on a word.

    Defined via :func:`token_spans` so the word list and the spans can never
    drift out of sync.
    """
    return [text[s:e] for s, e in token_spans(text)]
