"""UI-agnostic RSVP core: tokenizing text and scheduling word display.

Nothing in this sub-package imports a GUI toolkit. It can be driven by the
tkinter front-end today, or any other host (different toolkit, embedded
hardware) later.
"""

from .tokenizer import tokenize, token_spans, paragraph_end_indices
from .engine import RsvpEngine
from .pivot import pivot_index
from .chapters import find_chapters

__all__ = [
    "tokenize",
    "token_spans",
    "paragraph_end_indices",
    "RsvpEngine",
    "pivot_index",
    "find_chapters",
]
