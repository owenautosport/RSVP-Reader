"""RSVP Pocket E-Reader.

A minimal, offline, distraction-free speed reader that presents one word at a
time (Rapid Serial Visual Presentation).

The package is split so the reading/timing logic stays independent of any UI:

    rsvp.core   -- UI-agnostic engine and tokenizer (no GUI imports)
    rsvp.books  -- loading book files into plain text (isolated parsers)
    rsvp.ui     -- the tkinter desktop front-end (current host)
"""

__version__ = "1.1.1"
