# RSVP Pocket E-Reader

A minimal, quiet, fully-offline speed reader. It shows one word at a time,
centered, at a speed you choose (RSVP — Rapid Serial Visual Presentation), so
your eyes stay still and the words come to you. It does one thing — focused
reading of local books — and otherwise gets out of the way.

Desktop counterpart (developed on macOS) to the open-source RSVP Nano pocket
reader. Eventually targeted at a small landscape pocket screen; the hardware is
not yet decided, so the reading/timing logic is kept separate from the UI.

## Run

No installation, no dependencies — just Python 3 (with tkinter, which ships
with the standard python.org build on macOS):

```sh
python3 -m rsvp                 # opens the bundled sample book
python3 -m rsvp path/to/book.txt
```

## Controls

| Key       | Action                         |
|-----------|--------------------------------|
| `space`   | play / pause                   |
| `← / →`   | step back / forward one word   |
| `↑ / ↓`   | speed up / down (25 wpm)       |
| `r`       | restart from the beginning     |
| `o`       | open a book                    |
| `p`       | toggle pivot (ORP) alignment   |
| `h`       | hide / show the status line    |
| `q` / esc | quit                           |

## Stack & layout

Python 3 + tkinter. tkinter ships with Python, so the app has **zero**
third-party dependencies and is offline by construction.

```
rsvp/
  core/    UI-agnostic engine + tokenizer + ORP pivot (no GUI imports) -- reusable on any host
  books/   loading book files into plain text (isolated parsers; .txt for now)
  ui/      tkinter front-end: owns the window, keyboard, and timer
samples/   a short original sample book
```

The core engine owns no timer: it computes per-word timing (with small pauses
after sentences, clauses, and long words) and the host drives the ticking. That
boundary is what lets the engine move to different controls or hardware later.

## Status

Early MVP: plain-text books, adjustable speed, play/pause, step, restart, and
optimal-recognition-point (ORP) pivot alignment that pins a highlighted focal
letter in place so the eye stays still (toggle with `p`). EPUB/PDF parsing and
position memory are planned next.
