"""Turn raw book text into the sequence of words shown one-at-a-time.

Kept deliberately small and dependency-free. The only rule for now is "split on
whitespace", which is correct for the plain-text books the MVP loads. Smarter
handling (very long words, hyphenation, numbers) can grow here later without the
engine or UI needing to change.
"""

from __future__ import annotations


def tokenize(text: str) -> list[str]:
    """Split ``text`` into a flat list of display words.

    Whitespace (spaces, tabs, newlines) is collapsed and used purely as a
    separator, so paragraph breaks do not produce empty tokens. The original
    punctuation attached to each word is preserved, because the engine uses it
    to decide how long to linger on a word.
    """
    return text.split()
