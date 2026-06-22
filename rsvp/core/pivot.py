"""Optimal Recognition Point (ORP) — the pivot letter to anchor a word on.

RSVP readers feel calmest when the eye never moves. Centering each word defeats
that, because a word's recognition point lands in a different horizontal spot
every time. Instead we pick one pivot letter per word and let the host pin that
letter to a fixed position on screen, so the eye stays still.

This is pure logic with no UI: ``pivot_index`` returns the 0-based index of the
pivot character within the word, using the length-based rule popularized by
Spritz and used by RSVP Nano.
"""

from __future__ import annotations


def pivot_index(word: str) -> int:
    """Return the 0-based index of the pivot letter in ``word``.

    Empty input returns 0. The pivot sits just left of center and drifts
    rightward as words get longer:

        length 1        -> 0
        length 2..5     -> 1
        length 6..9     -> 2
        length 10..13   -> 3
        length 14+      -> 4
    """
    n = len(word)
    if n <= 1:
        return 0
    if n <= 5:
        return 1
    if n <= 9:
        return 2
    if n <= 13:
        return 3
    return 4
