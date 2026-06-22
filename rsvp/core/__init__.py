"""UI-agnostic RSVP core: tokenizing text and scheduling word display.

Nothing in this sub-package imports a GUI toolkit. It can be driven by the
tkinter front-end today, or any other host (different toolkit, embedded
hardware) later.
"""

from .tokenizer import tokenize, token_spans
from .engine import RsvpEngine
from .pivot import pivot_index

__all__ = ["tokenize", "token_spans", "RsvpEngine", "pivot_index"]
