"""tkinter desktop front-end for the RSVP reader.

This is the current *host*: it owns the window, the keyboard, and the real
timer. All reading and timing policy lives in ``rsvp.core``; the UI only renders
the current word and schedules the next tick.
"""

from .app import RsvpApp, run

__all__ = ["RsvpApp", "run"]
