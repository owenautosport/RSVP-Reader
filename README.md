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

The target device has **3 physical top buttons** plus a **touchscreen**. On the
Mac those are stood in for by keys (the buttons) and the mouse (touch), so the
whole interaction model is testable now.

**3 buttons** — context-sensitive (transport while reading, list navigation in a
menu):

| Button | Key | Reading screen | In a menu |
|--------|-----|----------------|-----------|
| Left   | `,` | slower         | move up   |
| Middle | `space` | play / pause | select   |
| Right  | `.` | faster         | move down |

**Touch** (mouse on the Mac):

| Gesture | Reading screen | In a menu |
|---------|----------------|-----------|
| tap     | open menu      | choose the tapped item |
| swipe ◀ | rewind a sentence | — |
| swipe ▶ | skip a sentence | back |
| swipe ▲▼ | — | scroll the list |

**Keyboard conveniences** (Mac dev): `← / →` step a word, `[ / ]` rewind / skip a
sentence, `↑ / ↓` speed, `m` menu, `tab` read-normally, `f` font, `p` pivot,
`r` restart, `o` open, `h` hide status, `q` / `esc` quit (esc also backs out of a
menu or the reading view).

`[` re-reads from the start of the current sentence (press again to step back
sentence by sentence) — RSVP otherwise removes the ability to glance back, which
matters for comprehension. Your **reading position, speed, font, and pivot
setting are saved automatically** (your place is the furthest point you reached,
saved continuously as you read, so going back to re-read never loses it and a
book always reopens where you got to — however the app was closed).

In the **read-normally** view the whole book is shown as an ordinary wrapped
paragraph with your current word highlighted and scrolled into view — for
finding your place or re-reading something you missed. **Click any word** to set
where RSVP resumes, then press `tab` (or `esc`) to go back.

## Stack & layout

Python 3 + tkinter. tkinter ships with Python, so the app has **zero**
third-party dependencies and is offline by construction.

```
rsvp/
  core/    UI-agnostic engine + tokenizer + ORP pivot (no GUI imports) -- reusable on any host
  nav/     UI-agnostic navigation: input model (buttons/swipes), menu, screen state machine
  books/   loading book files into plain text (isolated parsers; .txt for now)
  store.py local-only persistence (reading position + settings)
  ui/      tkinter front-end: window, timer, and the device input mapping
samples/   a short original sample book
```

The input model (`nav`) is deliberately toolkit-agnostic so the same menu logic
maps onto the Mac (keys + mouse) today and the device's 3 buttons + touchscreen
later — only the thin mapping in `ui/` changes.

The core engine owns no timer: it computes per-word timing — longer pauses at
paragraph ends, sentence ends, and clauses, plus a touch more time for long and
less-common words (a small bundled common-word list is the familiarity signal) —
and the host drives the ticking. That boundary is what lets the engine move to
different controls or hardware later.

## Status

Early MVP: plain-text books, adjustable speed, play/pause, word + sentence
navigation (rewind to re-read), paragraph and clause pauses, difficulty-aware
timing (longer for long and less-common words), restart, ORP pivot alignment
(`p`), switchable fonts (`f`), a read-normally paragraph view (`tab`), a
device-style 3-button + touch input model with a main **menu**, a **Library**
to pick books from local folders, a **Chapters / progress** jump screen, and
**saved reading position + settings** per book.

Drop your own `.txt` books in `~/.rsvp-reader/books/` and they appear in the
Library. Chapters detects headings (`Chapter 4`, `# Title`, `Prologue`…) and
falls back to progress markers (0–90%) when a book has none, marking where you
currently are. Settings adjusts speed, font, and pivot (tap a row to change it).
Menu sections still to build: Stats, About — plus EPUB/PDF parsing.
