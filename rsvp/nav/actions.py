"""Raw, hardware-faithful input events.

We model what the *device* physically produces, not what it means — meaning is
decided by the current screen (see the front-end's dispatcher). This keeps the
mapping honest: a button is just a button; a tap is just a tap.

    Button : the 3 physical top buttons (LEFT, MIDDLE, RIGHT)
    Swipe  : a directional touch drag

A plain tap carries coordinates, so it is delivered as ``(x, y)`` rather than an
enum member.
"""

from __future__ import annotations

from enum import Enum, auto


class Button(Enum):
    LEFT = auto()    # physically the "Slower" / up button
    MIDDLE = auto()  # physically the "Play/Pause" / select button
    RIGHT = auto()   # physically the "Faster" / down button


class Swipe(Enum):
    UP = auto()
    DOWN = auto()
    LEFT = auto()
    RIGHT = auto()
