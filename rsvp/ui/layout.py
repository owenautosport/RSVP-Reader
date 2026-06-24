"""Pure layout math: how the reading text scales with the window size.

No tkinter import, so it's unit-testable without a display. The reading text (the
big RSVP word and the read-normally paragraph) grows and shrinks in proportion to
the window, clamped to stay legible at small sizes and sane at large ones.
"""

from __future__ import annotations

# Design baseline: at a 640x340 window the word is 56pt and the paragraph 16pt.
# Scaling keeps that proportion as the window changes.
_BASE_W, _BASE_H = 640, 340
_BASE_WORD, _WORD_MIN, _WORD_MAX = 56, 24, 200
_BASE_READING, _READING_MIN, _READING_MAX = 16, 12, 40


def _scale(width: int, height: int) -> float:
    """Uniform scale vs the baseline window, limited by whichever dimension is
    tighter so a single centred line never overflows."""
    return min(width / _BASE_W, height / _BASE_H)


def word_font_size(width: int, height: int) -> int:
    size = round(_BASE_WORD * _scale(width, height))
    return max(_WORD_MIN, min(_WORD_MAX, size))


def reading_font_size(width: int, height: int) -> int:
    size = round(_BASE_READING * _scale(width, height))
    return max(_READING_MIN, min(_READING_MAX, size))
