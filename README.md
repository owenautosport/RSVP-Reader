# RSVP Pocket E-Reader

A minimal, quiet, fully-offline speed reader. It shows one word at a time,
centered, at a speed you choose (RSVP — Rapid Serial Visual Presentation), so
your eyes stay still and the words come to you. It does one thing — focused
reading of local books — and otherwise gets out of the way.

Desktop counterpart (developed on macOS) to the open-source RSVP Nano pocket
reader. Eventually targeted at a small landscape pocket screen; the hardware is
not yet decided, so the reading/timing logic is kept separate from the UI.

## Install (Windows, macOS & Linux)

Download for your system from the
[**Releases**](https://github.com/owenautosport/RSVP-Reader/releases) page:

- **Windows** — run `RSVP-Pocket-Reader-<version>-Setup.exe` (a standard
  next-next-finish wizard).
- **macOS** — open `RSVP-Pocket-Reader-<version>-macOS.dmg` and drag the app to
  Applications.
- **Linux** — make `RSVP-Pocket-Reader-<version>-x86_64.AppImage` executable
  (`chmod +x`) and run it; no installation needed.

The app is fully self-contained — no separate Python install needed, and PDF
support is included.

## Run from source

Just Python 3 (with tkinter, which ships with the standard python.org build on
macOS). `.txt` and `.epub` need **no third-party packages**:

```sh
python3 -m rsvp                 # opens the bundled sample book
python3 -m rsvp path/to/book.epub
```

Reading `.pdf` books additionally needs `pypdf` (pure Python, offline once
installed): `pip install pypdf` (or `pip install -r requirements.txt`).

## Build the installers

PyInstaller bundles the app; the OS-native installer wraps it. Building happens
on each OS (a Windows `.exe` can't be built from macOS), so CI does both:
pushing a `vX.Y.Z` tag runs `.github/workflows/release.yml`, which builds on
Windows + macOS runners and publishes the installers to a GitHub Release.

Locally:

```sh
pip install pyinstaller pypdf
# macOS: builds the .app and a drag-to-install .dmg into ./installer
bash packaging/build_macos.sh
# Linux: builds a portable .AppImage into ./installer
bash packaging/build_linux.sh
# Windows: build the app, then compile the wizard with Inno Setup
pyinstaller --noconfirm packaging/rsvp.spec
iscc /DAppVersion=1.0.0 packaging\installer.iss
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
| swipe ▶ | —              | back |
| swipe ▲▼ | —             | scroll the list |

The reading screen is intentionally bare: speed and play/pause are the side
buttons, and a tap opens the menu — that's it. Speed, font, and pivot are set in
**Settings**.

**Keyboard conveniences** (Mac dev): `↑ / ↓` speed, `m` menu, `tab` read-normally,
`r` restart, `h` hide status, `q` / `esc` quit (esc also backs out of a menu or
the reading view).

Books are added by dropping `.txt` files where the Library scans (on the device,
a microSD card); there is no file-open dialog. The menu and Library are reachable
even when no book is loaded.

Your **reading position, speed, font, and pivot setting are saved automatically**
(your place is the furthest point you reached, saved continuously as you read, so
going back to re-read never loses it and a book always reopens where you got to —
however the app was closed).

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
  books/   loading book files into text + chapter structure (.txt, .epub, .pdf; isolated parsers)
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

**v1.0 — the desktop (Windows & macOS) edition.** A polished, installable PC
app and the proving ground for the eventual pocket device; the reading/timing
core and the 3-button + touch input model are kept separate so they port to
hardware later.

Features: plain-text books, adjustable speed, play/pause, word + sentence
navigation (rewind to re-read), paragraph and clause pauses, difficulty-aware
timing (longer for long and less-common words), restart, ORP pivot alignment
(`p`), switchable fonts (`f`), a read-normally paragraph view (`tab`), a
device-style 3-button + touch input model with a main **menu**, a **Library**
to pick books from local folders, a **Chapters / progress** jump screen, and
**saved reading position + settings** per book.

Drop your own `.txt` books in `~/.rsvp-reader/books/` and they appear in the
Library. Chapters detects headings (`Chapter 4`, `# Title`, `Prologue`…) and
falls back to progress markers (0–90%) when a book has none, marking where you
currently are. Settings adjusts speed, font, pivot, brightness, low-power mode, auto-off time,
and where the battery shows (tap a row to change it). Stats shows your progress
and total time read for the current book; About shows version, library, and
storage used / capacity. An iPhone-style battery indicator sits in the top-right
— on every page or only on About, per the setting.

**EPUB** books are supported alongside `.txt` (parsed with the standard library
only — `zipfile` + `xml.etree` + `html.parser`, no dependencies), with real
chapters read from the book's spine. **PDF** is also supported via the optional
`pypdf` package (chapters from the PDF outline when present); `.txt`/`.epub`
remain dependency-free.

Battery level is read per-OS (`rsvp/battery.py`: `pmset` on macOS,
`GetSystemPowerStatus` on Windows, `/sys` on Linux). Screen brightness (window
opacity standing in for a backlight), low-power mode, and the auto-off sleep
timer are desktop stand-ins that the hardware port maps to the device's real
gauge, backlight, and power controls.
