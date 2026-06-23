"""The tkinter front-end: window, timer, input mapping, and screen rendering.

Layout is deliberately almost-empty: one large word, centered, on a dark
background, with two faint tip/status bars that can be hidden. The window owns
the real timer; on each word it asks the engine how long to wait, schedules a
single ``after`` callback, and advances.

Input is modelled on the target device — 3 physical top buttons plus a
touchscreen — via the toolkit-agnostic ``rsvp.nav`` layer. On the Mac the mouse
stands in for touch (press+release → tap/swipe) and three keys for the buttons.
A ``Navigator`` tracks whether the reading screen or a menu is showing; reading
position and settings persist locally through ``rsvp.store``.
"""

from __future__ import annotations

import bisect
import shutil
import sys
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, font as tkfont

from ..books import (
    BookLoadError,
    SUPPORTED_EXTENSIONS,
    book_title,
    find_books,
    load_book_full,
)
from ..core import (
    RsvpEngine,
    find_chapters,
    paragraph_end_indices,
    pivot_index,
    tokenize,
    token_spans,
)
from .. import __version__
from ..battery import read_battery
from ..nav import Button, Menu, MenuItem, Navigator, Screen, Swipe
from ..store import Store, book_key

# Quiet, low-contrast palette so the word is the only thing that stands out.
_BG = "#111111"
_FG = "#f2f2f2"
_DIM = "#666666"
_PIVOT = "#e8643c"   # the one highlighted pivot letter / menu selection
_GUIDE = "#333333"   # faint tick marks framing the pivot column

# Main menu: id -> intent the app acts on. Built sections are enabled; the rest
# are visible-but-dimmed so the structure is clear in the app.
_MENU_ITEMS = [
    MenuItem("resume", "Resume"),
    MenuItem("library", "Library"),
    MenuItem("chapters", "Chapters"),
    MenuItem("settings", "Settings"),
    MenuItem("stats", "Stats"),
    MenuItem("about", "About"),
]

# Speed choices the Settings page cycles through (tap to step up, wraps round).
# Fine 25-wpm nudges are still available while reading via the side buttons.
_SPEED_PRESETS = (150, 200, 250, 300, 350, 400, 450, 500, 600, 700, 800, 1000)

# iPhone-style battery indicator colours and how often to re-read the level.
_BATT_OUTLINE = "#9a9a9a"
_BATT_OK = _PIVOT       # accent orange, matching the pivot letter
_BATT_LOW = "#ff3b30"
_BATT_POLL_MS = 60_000


def _rounded_rect(canvas, x1, y1, x2, y2, r, **kw):
    """A rounded rectangle on a Canvas (smoothed polygon)."""
    pts = [
        x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r,
        x2, y2 - r, x2, y2, x2 - r, y2, x1 + r, y2,
        x1, y2, x1, y2 - r, x1, y1 + r, x1, y1,
    ]
    return canvas.create_polygon(pts, smooth=True, **kw)

# When a book has no detectable chapters, the Chapters screen falls back to this
# many evenly-spaced progress markers (0%, 10%, ... ) to jump by.
_PROGRESS_SEGMENTS = 10

# Save the reading position every this many words while playing, so a book
# resumes where you left off even if the app is force-quit (e.g. ⌘Q) without the
# normal close handler running.
_AUTOSAVE_EVERY = 20

def _resource_root() -> Path:
    """Folder holding bundled resources (the ``samples/`` dir).

    In a PyInstaller build the data is unpacked next to the executable
    (``sys._MEIPASS``); in a normal checkout it's the repo root."""
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parents[2]


# Where the bundled sample book lives, used by the Library.
_SAMPLES_DIR = _resource_root() / "samples"
# A user drop-folder for their own books (cross-platform: ~ resolves per-OS).
_USER_BOOKS_DIR = Path.home() / ".rsvp-reader" / "books"
_MENU_ROW_H = 40  # pixel height of a menu row (also used for tap hit-testing)

# Settings cycles.
_BRIGHTNESS_PRESETS = (25, 50, 75, 100)        # percent
_AUTOOFF_PRESETS = (0, 1, 5, 15, 30)           # minutes; 0 = never
_AUTOOFF_CHECK_MS = 3000                        # how often to check for idle

# Touch gesture thresholds (pixels): below the tap radius is a tap, past the
# swipe minimum is a directional swipe.
_TAP_RADIUS = 16
_SWIPE_MIN = 32

# "Read normally" overlay: calmer, smaller body text than the giant RSVP word.
_READING_FG = "#c9c9c9"
_READING_HL_BG = "#e8643c"   # background of the current word in the paragraph
_READING_HL_FG = "#111111"   # text of that highlighted word

# Where the pivot letter is pinned horizontally (fraction of window width).
# Just left of center leaves room for the usually-longer word tail.
_PIVOT_RELX = 0.45

# Word fonts the reader can cycle through (sans, serif, mono, wide sans, serif).
# Picked per-platform so each family exists; Tk falls back gracefully anyway.
# ("Helvetica"/"Times"/"Courier" are portable Tk aliases.)
if sys.platform == "darwin":
    _WORD_FONTS = ("Helvetica", "Georgia", "Menlo", "Verdana", "Palatino")
elif sys.platform.startswith("win"):
    _WORD_FONTS = ("Segoe UI", "Georgia", "Consolas", "Verdana", "Palatino Linotype")
else:
    _WORD_FONTS = ("Helvetica", "DejaVu Serif", "DejaVu Sans Mono", "Verdana", "Times")

_WPM_STEP = 25
# All control tips live on the bottom bar; the top line stays short (status +
# the corner battery), so nothing collides with the battery.
_TIPS = ("space play/pause    ↑/↓ speed    m menu    "
         "tab read    r restart    h hide    q quit")


class RsvpApp:
    def __init__(self, book_path: str | Path | None = None) -> None:
        self.engine = RsvpEngine()
        self.store = Store()
        self.nav = Navigator({
            Screen.MENU: Menu(_MENU_ITEMS),
            Screen.LIBRARY: Menu([]),   # filled when the Library is opened
            Screen.CHAPTERS: Menu([]),  # filled when Chapters is opened
            Screen.SETTINGS: Menu([]),  # filled when Settings is opened
            Screen.STATS: Menu([]),     # info screen (rendered as plain lines)
            Screen.ABOUT: Menu([]),     # info screen
        })
        self._after_id: str | None = None
        self._words_since_save = 0
        self._furthest = 0  # furthest word reached; what we resume to (re-reading won't lower it)
        self._book_seconds = 0.0       # cumulative reading time for the current book
        self._play_started: float | None = None  # monotonic time playback began
        self._show_status = True
        self._reading = False          # is the "read normally" overlay open?
        self._placeholder = "—"
        self._book_name = ""
        self._book_path: Path | None = None  # current book, for saving position
        self._menu_hint = ""
        self._press: tuple[int, int] | None = None  # gesture start point
        self._info_title = ""          # Stats / About screen contents
        self._info_lines: list = []    # each item: a str (centred) or (label, value)
        self._raw_text = ""            # original text, for the reading overlay
        self._span_starts: list[int] = []  # start offset of each word (for clicks)
        self._spans: list[tuple[int, int]] = []
        self._epub_chapters: list[tuple[str, int]] = []  # (title, word index)
        self._remove_mode = False      # Library: tapping a book removes it

        # Restore saved settings or defaults.
        s = self.store.get_settings(
            {"wpm": self.engine.wpm, "font_index": 0, "orp": True,
             "battery_always": True, "brightness": 100, "low_power": False,
             "auto_off_min": 0}
        )
        self.engine.wpm = int(s["wpm"])
        self._font_idx = int(s["font_index"]) % len(_WORD_FONTS)
        self._orp_enabled = bool(s["orp"])
        self._battery_always = bool(s["battery_always"])  # show on all pages vs About only
        self._battery: tuple[int, bool] | None = None
        self._brightness = int(s["brightness"])
        self._low_power = bool(s["low_power"])
        self._auto_off_min = int(s["auto_off_min"])
        self._last_activity = time.monotonic()
        self._asleep = False

        self.root = tk.Tk()
        self.root.title("RSVP Pocket E-Reader")
        self.root.configure(bg=_BG)
        self.root.geometry("640x340")  # compact, landscape — closer to the target screen
        self.root.minsize(360, 200)
        self.root.protocol("WM_DELETE_WINDOW", self._quit)

        self._word_font = tkfont.Font(family=_WORD_FONTS[self._font_idx], size=56, weight="bold")
        self._status_font = tkfont.Font(family="Helvetica", size=11)
        self._reading_font = tkfont.Font(family="Georgia", size=16)
        self._menu_font = tkfont.Font(family="Helvetica", size=22)
        self._info_font = tkfont.Font(family="Helvetica", size=14)

        # A canvas (not a Label) so the pivot letter can be pinned to a fixed
        # x-position regardless of word length. Fills the window; the status
        # line sits on top of it.
        self.canvas = tk.Canvas(self.root, bg=_BG, highlightthickness=0)
        self.canvas.place(relx=0, rely=0, relwidth=1, relheight=1)
        self.canvas.bind("<Configure>", lambda e: self._render())
        # Mouse stands in for the touchscreen: press+release becomes tap/swipe.
        self.canvas.bind("<ButtonPress-1>", self._on_press)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)

        # Two thin tip/status bars framing the word: top and bottom.
        self.top_bar = tk.Label(
            self.root, text="", font=self._status_font, fg=_DIM, bg=_BG, anchor="center"
        )
        self.top_bar.place(relx=0.5, rely=0.07, anchor="center")
        self.bottom_bar = tk.Label(
            self.root, text="", font=self._status_font, fg=_DIM, bg=_BG, anchor="center"
        )
        self.bottom_bar.place(relx=0.5, rely=0.93, anchor="center")

        # iPhone-style battery indicator, drawn on its own tiny canvas pinned to
        # the top-right corner. Shown on every page or only on About (a setting).
        self._batt_font = tkfont.Font(family="Helvetica", size=8, weight="bold")
        self.battery_canvas = tk.Canvas(
            self.root, width=44, height=16, bg=_BG, highlightthickness=0
        )

        # Auto-off "screen": a black layer shown after the idle timeout; any
        # touch or key wakes it.
        self.sleep_overlay = tk.Frame(self.root, bg="#000000", cursor="none")
        self.sleep_overlay.bind("<Button-1>", lambda e: self._wake())
        self.sleep_overlay.bind("<Key>", lambda e: (self._wake(), "break")[1])

        # "Read normally" overlay: the whole book as a wrapped paragraph, shown
        # on top of everything only while toggled on. Read-only; click a word to
        # set where RSVP resumes.
        self.reading = tk.Text(
            self.root, wrap="word", bg=_BG, fg=_READING_FG, font=self._reading_font,
            relief="flat", highlightthickness=0, padx=48, pady=44, cursor="arrow",
            spacing1=2, spacing2=4, spacing3=10, insertontime=0,
        )
        self.reading.tag_configure(
            "current", background=_READING_HL_BG, foreground=_READING_HL_FG
        )
        self.reading.bind("<Button-1>", self._on_reading_click)
        self.reading.bind("<Tab>", lambda e: self._toggle_reading_view() or "break")
        self.reading.bind("<Escape>", lambda e: self._close_reading_view() or "break")
        self.reading.bind("<q>", lambda e: self.root.destroy())

        self._bind_keys()

        if book_path is not None:
            self._open_path(Path(book_path))
        else:
            self._render()
            self._update_status()

        self._apply_brightness()
        self._poll_battery()    # first read + schedule periodic refresh
        self._check_auto_off()  # schedule the idle check

    # -- setup -----------------------------------------------------------

    def _bind_keys(self) -> None:
        r = self.root
        # The 3 physical top buttons, mapped to keys on the Mac. Their meaning is
        # context-sensitive (see _on_button): transport while reading, list
        # navigation while in a menu.
        r.bind("<comma>", lambda e: self._on_button(Button.LEFT))    # Slower / Up
        r.bind("<space>", lambda e: self._on_button(Button.MIDDLE))  # Play·Pause / Select
        r.bind("<period>", lambda e: self._on_button(Button.RIGHT))  # Faster / Down
        r.bind("<Return>", lambda e: self._on_button(Button.MIDDLE))
        r.bind("<m>", lambda e: self._toggle_menu())

        # Reading-screen conveniences (keyboard only; the device uses buttons +
        # touch). All no-op while a menu or the reading overlay is open.
        r.bind("<Up>", lambda e: self._change_speed(+_WPM_STEP))
        r.bind("<Down>", lambda e: self._change_speed(-_WPM_STEP))
        r.bind("<r>", lambda e: self._restart())
        r.bind("<Tab>", lambda e: self._toggle_reading_view() or "break")
        r.bind("<h>", lambda e: self._toggle_status())
        r.bind("<q>", lambda e: self._quit())
        r.bind("<Escape>", lambda e: self._on_escape())

    # -- input dispatch (buttons + touch, context-sensitive) ------------

    def _on_button(self, btn: Button) -> None:
        if self._note_activity():  # first press just wakes from auto-off
            return
        if self._reading:  # the paragraph overlay owns input while open
            return
        if self.nav.in_menu:
            if btn is Button.LEFT:
                self._menu_move(-1)
            elif btn is Button.RIGHT:
                self._menu_move(1)
            else:  # MIDDLE = select
                self._menu_select()
        else:
            if btn is Button.LEFT:
                self._change_speed(-_WPM_STEP)
            elif btn is Button.RIGHT:
                self._change_speed(+_WPM_STEP)
            else:  # MIDDLE = play/pause
                self._toggle()

    def _on_press(self, event: tk.Event) -> None:
        self._press = (event.x, event.y)

    def _on_release(self, event: tk.Event) -> None:
        if self._press is None:
            return
        x0, y0 = self._press
        self._press = None
        dx, dy = event.x - x0, event.y - y0
        if abs(dx) < _TAP_RADIUS and abs(dy) < _TAP_RADIUS:
            self._on_tap(event.x, event.y)
        elif max(abs(dx), abs(dy)) >= _SWIPE_MIN:
            if abs(dx) > abs(dy):
                self._on_swipe(Swipe.RIGHT if dx > 0 else Swipe.LEFT)
            else:
                self._on_swipe(Swipe.DOWN if dy > 0 else Swipe.UP)

    def _on_tap(self, x: int, y: int) -> None:
        if self._note_activity():
            return
        if self._reading:
            return
        if self.nav.in_menu:
            if self.nav.screen in (Screen.STATS, Screen.ABOUT):
                self._menu_back()  # any tap leaves an info page
                return
            idx = self._menu_index_at_y(y)
            if idx is None:
                return
            item = self.nav.menu.items[idx]
            if not item.enabled:
                if self.nav.screen is Screen.MENU:
                    self._menu_hint = f"{item.label} — coming soon"
                    self._update_status()
                return
            self.nav.menu.select_index(idx)
            self._render()
            self._menu_select()
        else:
            self._open_menu()  # tap the word to step out into the menu

    def _on_swipe(self, swipe: Swipe) -> None:
        if self._note_activity():
            return
        if self._reading:
            return
        if self.nav.in_menu:
            if swipe is Swipe.UP:
                self._menu_move(-1)
            elif swipe is Swipe.DOWN:
                self._menu_move(1)
            elif swipe is Swipe.RIGHT:
                self._menu_back()  # swipe right = back one screen
        # Reading screen has no swipe actions; speed/play are the side buttons.

    def _on_escape(self) -> None:
        if self._reading:
            self._close_reading_view()
        elif self.nav.in_menu:
            self._menu_back()
        else:
            self._quit()

    def _controls_locked(self) -> bool:
        """Reading-screen controls are inert while a menu/overlay is showing."""
        return self._reading or self.nav.in_menu

    # -- book loading ----------------------------------------------------

    def _open_path(self, path: Path) -> None:
        self._save_position()  # remember where we were in the previous book
        try:
            book = load_book_full(path)
        except BookLoadError as exc:
            self._book_name = ""
            self._book_path = None
            self.engine.load([])
            self._raw_text = ""
            self._spans = []
            self._span_starts = []
            self._epub_chapters = []
            self._placeholder = "⚠"
            self._render()
            self.top_bar.config(text=str(exc))
            self.bottom_bar.config(text=_TIPS)
            return
        text = book.text
        self._placeholder = "—"
        self._raw_text = text
        self._spans = token_spans(text)
        self._span_starts = [s for s, _ in self._spans]
        # Real chapters from the file's structure (EPUB) -> word indices.
        self._epub_chapters = []
        for title, offset in book.chapters:
            wi = self._word_index_at_offset(offset)
            if wi is not None:
                self._epub_chapters.append((title, wi))
        resume_at = self.store.get_position(path)  # 0 if never opened before
        self.engine.load(
            tokenize(text),
            start_index=resume_at,
            paragraph_ends=paragraph_end_indices(text),
        )
        self._book_path = path
        self._book_name = path.stem
        # Cache the display title once (parsing metadata here is fine; we just
        # loaded the whole book) so listing the Library never parses files.
        if not self.store.get_title(path):
            self.store.set_title(path, book_title(path))
        self._furthest = resume_at  # resume point is the furthest reached so far
        self._book_seconds = self.store.get_seconds(path)
        self._play_started = None
        self._render()
        self._update_status()

    # -- persistence -----------------------------------------------------

    def _save_position(self) -> None:
        self._words_since_save = 0
        self._fold_time()
        if self._book_path is not None and self.engine.total_words:
            # Resume to the furthest point reached, not wherever the cursor is
            # now — so going back to re-read never loses your place.
            self._furthest = max(self._furthest, self.engine.index)
            self.store.set_position(self._book_path, self._furthest)
            self.store.set_seconds(self._book_path, self._book_seconds)
            self.store.save()

    def _save_settings(self) -> None:
        self.store.set_settings({
            "wpm": self.engine.wpm,
            "font_index": self._font_idx,
            "orp": self._orp_enabled,
            "battery_always": self._battery_always,
            "brightness": self._brightness,
            "low_power": self._low_power,
            "auto_off_min": self._auto_off_min,
        })
        self.store.save()

    def _quit(self) -> None:
        self._save_position()
        self._save_settings()
        self.root.destroy()

    # -- playback control ------------------------------------------------

    def _toggle(self) -> None:
        if self._controls_locked():
            return
        if self.engine.is_playing:
            self._pause()
        else:
            self._play()

    def _play(self) -> None:
        if self._controls_locked() or not self.engine.total_words:
            return
        self.engine.play()
        self._play_started = time.monotonic()
        self._cancel_pending()
        self._tick()
        self._update_status()

    def _fold_time(self) -> None:
        """Add elapsed playback time to the book's total; keep the clock running
        only while still playing."""
        if self._play_started is not None:
            now = time.monotonic()
            self._book_seconds += now - self._play_started
            self._play_started = now if self.engine.is_playing else None

    def _pause(self) -> None:
        self.engine.pause()
        self._cancel_pending()
        self._save_position()
        self._render()
        self._update_status()

    def _tick(self) -> None:
        """Show the current word, then schedule advancing to the next one."""
        self._after_id = None
        if not self.engine.is_playing:
            return
        self._render()
        delay = self.engine.current_delay_ms
        self._after_id = self.root.after(delay, self._on_word_elapsed)

    def _on_word_elapsed(self) -> None:
        if not self.engine.is_playing:
            return
        if self.engine.advance():
            self._words_since_save += 1
            self._furthest = max(self._furthest, self.engine.index)
            if self._words_since_save >= _AUTOSAVE_EVERY:
                self._save_position()
            self._tick()
        else:  # reached the last word
            self.engine.pause()
            self._save_position()
            self._render()
            self._update_status()

    def _cancel_pending(self) -> None:
        if self._after_id is not None:
            self.root.after_cancel(self._after_id)
            self._after_id = None

    # -- speed & display -------------------------------------------------

    def _restart(self) -> None:
        if self._controls_locked():
            return
        self._pause()
        self.engine.restart()
        self._render()
        self._update_status()

    def _change_speed(self, delta: int) -> None:
        if self._controls_locked():
            return
        self.engine.adjust_wpm(delta)
        self._save_settings()
        self._update_status()

    def _toggle_status(self) -> None:
        self._show_status = not self._show_status
        self._update_status()

    # -- main menu -------------------------------------------------------

    def _toggle_menu(self) -> None:
        if self._reading:
            return
        self._close_menu() if self.nav.in_menu else self._open_menu()

    def _open_menu(self) -> None:
        # Reachable even with no book loaded, so the Library is always available.
        self._pause()
        self._menu_hint = "tap an item to choose    ·    swipe ▶ / esc  back"
        self.nav.open(Screen.MENU)
        self._render()
        self._update_status()

    def _close_menu(self) -> None:
        """Collapse all the way back to the reading screen."""
        self.nav.go_reading()
        self._render()
        self._update_status()

    def _menu_back(self) -> None:
        """Step back one screen (Library -> Menu -> Reading)."""
        self.nav.back()
        self._render()
        self._update_status()

    def _library_dirs(self) -> list[Path]:
        dirs = [_SAMPLES_DIR, _USER_BOOKS_DIR]
        if self._book_path is not None:
            dirs.append(self._book_path.parent)
        return dirs

    def _open_library(self) -> None:
        books = find_books(self._library_dirs())
        current = book_key(self._book_path) if self._book_path else None
        current_idx = None
        items: list[MenuItem] = []
        # Titles come from the cache (set when a book is opened) — never parse
        # files while listing, so the Library opens instantly.
        if self._remove_mode:
            for p in books:
                title = self.store.get_title(p) or self._cheap_title(p)
                items.append(MenuItem(str(p), f"✕  {title}"))
            items.append(MenuItem("__done__", "Cancel"))  # at the bottom
            self._menu_hint = "tap a book to remove it    ·    Cancel / esc  back"
        else:
            items.append(MenuItem("__add__", "＋  Add a book…"))  # at the top
            for i, p in enumerate(books):
                if current is not None and book_key(p) == current:
                    current_idx = i + 1  # +1 for the Add row above
                title = self.store.get_title(p) or self._cheap_title(p)
                items.append(MenuItem(str(p), title))
            if books:
                items.append(MenuItem("__remove__", "−  Remove a book…"))  # at the bottom
            self._menu_hint = ("tap a book to read    ·    swipe ▶ / esc  back"
                               if books else
                               "tap ＋ to add a book    ·    swipe ▶ / esc  back")
        self.nav.open(Screen.LIBRARY, items=items)
        if current_idx is not None and not self._remove_mode:
            self.nav.menu.select_index(current_idx)  # start on the open book
        self._render()
        self._update_status()

    @staticmethod
    def _cheap_title(path: Path) -> str:
        """Title for an as-yet-unopened book: parse only small files inline so
        the Library never stalls on a large EPUB/PDF (those use the filename
        until opened, when the real title gets cached)."""
        try:
            if path.stat().st_size <= 1_500_000:
                return book_title(path)
        except OSError:
            pass
        return path.stem

    def _remove_book(self, path: Path) -> None:
        """Delete a user-added book from the library (never the bundled samples)."""
        try:
            in_library = path.resolve().parent == _USER_BOOKS_DIR.resolve()
        except OSError:
            in_library = False
        if not in_library:
            self._menu_hint = "built-in books can't be removed    ·    ✓ Done"
            self._update_status()
            return
        try:
            path.unlink()
        except OSError as exc:
            self._menu_hint = f"couldn't remove: {exc}"
            self._update_status()
            return
        self.store.remove_book(path)
        self.store.save()
        if self._book_path and path.resolve() == self._book_path.resolve():
            self._book_path = None  # stop saving position for the deleted book
        self._open_library()  # refresh, staying in remove mode
        self._menu_hint = f"removed “{path.stem}”    ·    tap another, or ✓ Done"
        self._update_status()

    def _add_book(self) -> None:
        """PC convenience: pick a book file and copy it into the library."""
        patterns = " ".join(f"*{ext}" for ext in SUPPORTED_EXTENSIONS)
        path = filedialog.askopenfilename(
            title="Add a book",
            filetypes=[("Books", patterns), ("All files", "*.*")],
        )
        if not path:
            self._render()  # dialog cancelled; stay on the Library
            return
        src = Path(path)
        dest = src
        try:
            _USER_BOOKS_DIR.mkdir(parents=True, exist_ok=True)
            target = _USER_BOOKS_DIR / src.name
            if src.resolve() != target.resolve():
                shutil.copy2(src, target)
            dest = target
        except OSError:
            dest = src  # couldn't copy; just open it in place
        self.nav.go_reading()
        self._open_path(dest)  # opens (and resumes) the new book
        self._render()
        self._update_status()
        self._render()
        self._update_status()

    def _chapter_targets(self) -> list[tuple[str, int]]:
        """(label, word-index) jump points: real chapters if detected, else
        evenly-spaced progress markers."""
        total = self.engine.total_words
        if not total:
            return []
        if self._epub_chapters:        # real structure from the EPUB
            return self._epub_chapters
        chapters = find_chapters(self._raw_text, self._span_starts)
        if chapters:
            return chapters
        last = total - 1
        marks = []
        for n in range(_PROGRESS_SEGMENTS):
            pct = n * 100 // _PROGRESS_SEGMENTS
            marks.append((f"{pct}%", round(pct / 100 * last)))
        return marks

    def _open_chapters(self) -> None:
        targets = self._chapter_targets()
        if not targets:
            return
        # The furthest chapter reached (the last one at/before the furthest word).
        here = max(self._furthest, self.engine.index)
        current = 0
        for i, (_, wi) in enumerate(targets):
            if wi <= here:
                current = i
        items = []
        for i, (label, _) in enumerate(targets):
            mark = "• " if i == current else ""   # the furthest chapter you've reached
            items.append(MenuItem(str(targets[i][1]), f"{mark}{label}"))
        self._menu_hint = "tap to jump    ·    swipe ▶ / esc  back"
        self.nav.open(Screen.CHAPTERS, items=items)
        self.nav.menu.select_index(current)  # land the cursor on the furthest chapter
        self._render()
        self._update_status()

    # -- settings screen -------------------------------------------------

    def _settings_items(self) -> list[MenuItem]:
        battery = "Always" if self._battery_always else "About only"
        return [
            MenuItem("set_speed", f"Speed:  {self.engine.wpm} wpm"),
            MenuItem("set_font", f"Font:  {_WORD_FONTS[self._font_idx]}"),
            MenuItem("set_pivot", f"Pivot (ORP):  {'On' if self._orp_enabled else 'Off'}"),
            MenuItem("set_brightness", f"Brightness:  {self._brightness}%"),
            MenuItem("set_lowpower", f"Low power:  {'On' if self._low_power else 'Off'}"),
            MenuItem("set_autooff", f"Auto-off:  {self._format_autooff()}"),
            MenuItem("set_battery", f"Battery:  {battery}"),
        ]

    def _format_autooff(self) -> str:
        return "Never" if not self._auto_off_min else f"{self._auto_off_min} min"

    def _open_settings(self) -> None:
        self._menu_hint = "tap a setting to change it    ·    swipe ▶ / esc  back"
        self.nav.open(Screen.SETTINGS, items=self._settings_items())
        self._render()
        self._update_status()

    def _apply_setting(self, setting_id: str) -> None:
        if setting_id == "set_speed":
            self.engine.wpm = self._next_speed(self.engine.wpm)
        elif setting_id == "set_font":
            self._font_idx = (self._font_idx + 1) % len(_WORD_FONTS)
            self._word_font.config(family=_WORD_FONTS[self._font_idx])
        elif setting_id == "set_pivot":
            self._orp_enabled = not self._orp_enabled
        elif setting_id == "set_brightness":
            self._brightness = self._next_in(_BRIGHTNESS_PRESETS, self._brightness)
            self._apply_brightness()
        elif setting_id == "set_lowpower":
            self._low_power = not self._low_power
            self._apply_brightness()  # low power dims a little; slower poll next cycle
        elif setting_id == "set_autooff":
            self._auto_off_min = self._next_in(_AUTOOFF_PRESETS, self._auto_off_min)
            self._last_activity = time.monotonic()
        elif setting_id == "set_battery":
            self._battery_always = not self._battery_always
            self._update_battery()
        self._save_settings()
        # Refresh the row labels in place, keeping the cursor where it was.
        idx = self.nav.menu.index
        self.nav.menu.set_items(self._settings_items())
        self.nav.menu.select_index(idx)
        self._render()
        self._update_status()

    @staticmethod
    def _next_speed(wpm: int) -> int:
        for preset in _SPEED_PRESETS:
            if preset > wpm:
                return preset
        return _SPEED_PRESETS[0]  # wrap round to the slowest

    # -- info screens (Stats / About) -----------------------------------

    def _show_info(self, screen: Screen, title: str, lines: list) -> None:
        self._info_title = title
        self._info_lines = lines
        self._menu_hint = "tap  ·  swipe ▶ / esc   back"
        self.nav.open(screen)
        self._render()
        self._update_status()

    def _open_stats(self) -> None:
        self._fold_time()  # count time up to now before reporting it
        total = self.engine.total_words
        if not total:
            lines = ["No book open.", "", "Pick one from the Library."]
        else:
            read = min(max(self._furthest, self.engine.index) + 1, total)
            pct = int(read / total * 100)
            left = total - read
            wpm = self.engine.wpm
            # (label, value) rows render with aligned colons; bare strings centre.
            lines = [
                self._book_name,
                "",
                ("Progress", f"{pct}%"),
                ("Read", f"{read:,} of {total:,} words"),
                ("Remaining", f"{left:,} words"),
                ("Time read", self._format_duration(self._book_seconds)),
                ("Time left", f"{self._format_minutes(left / wpm)} at {wpm} wpm"),
            ]
        self._show_info(Screen.STATS, "Stats", lines)

    def _open_about(self) -> None:
        books = find_books(self._library_dirs())
        n = len(books)
        used = sum(self._safe_size(p) for p in books)
        total = self._total_storage()
        storage = self._format_bytes(used)
        if total:
            storage += f" / {self._format_bytes(total)}"  # used of capacity
        lines = [
            "Flashes a book one word at a time at a speed",
            "you choose, so your eyes stay still and you",
            "read faster with less effort. Fully offline.",
            "",
            ("Version", __version__),
            ("Library", f"{n} book{'' if n == 1 else 's'}"),
            ("Storage", storage),
        ]
        self._show_info(Screen.ABOUT, "RSVP Pocket E-Reader", lines)

    @staticmethod
    def _safe_size(path: Path) -> int:
        try:
            return path.stat().st_size
        except OSError:
            return 0

    @staticmethod
    def _total_storage() -> int:
        """Total capacity of the storage holding the books (the SD card on the
        device); 0 if it can't be read."""
        for p in (_USER_BOOKS_DIR, _USER_BOOKS_DIR.parent, Path.home()):
            try:
                return shutil.disk_usage(p).total
            except OSError:
                continue
        return 0

    @staticmethod
    def _format_bytes(n: int) -> str:
        if n < 1024:
            return f"{n} B"
        if n < 1024 ** 2:
            return f"{n / 1024:.0f} KB"
        if n < 1024 ** 3:
            return f"{n / 1024 ** 2:.1f} MB"
        return f"{n / 1024 ** 3:.1f} GB"

    @staticmethod
    def _format_minutes(mins: float) -> str:
        if mins < 1:
            return "under a minute"
        mins = round(mins)
        if mins < 60:
            return f"~{mins} min"
        h, m = divmod(mins, 60)
        return f"~{h} h {m} min"

    @staticmethod
    def _format_duration(seconds: float) -> str:
        seconds = int(seconds)
        if seconds < 60:
            return f"{seconds} sec"
        minutes = seconds // 60
        if minutes < 60:
            return f"{minutes} min"
        h, m = divmod(minutes, 60)
        return f"{h} h {m} min"

    def _menu_move(self, delta: int) -> None:
        self.nav.move(delta)
        self._render()

    def _menu_select(self) -> None:
        if self.nav.screen in (Screen.STATS, Screen.ABOUT):
            self._menu_back()  # the select button also leaves an info page
            return
        intent = self.nav.select()
        if intent is None:
            return
        if self.nav.screen is Screen.LIBRARY:
            if intent == "__add__":
                self._add_book()
                return
            if intent == "__remove__":
                self._remove_mode = True
                self._open_library()
                return
            if intent == "__done__":
                self._remove_mode = False
                self._open_library()
                return
            if self._remove_mode:
                self._remove_book(Path(intent))
                return
            self.nav.go_reading()
            self._open_path(Path(intent))  # opens at its saved position
            self._render()
            self._update_status()
            return
        if self.nav.screen is Screen.CHAPTERS:
            self.engine.seek_to(int(intent))
            self.nav.go_reading()
            self._pause()  # also saves the new position
            return
        if self.nav.screen is Screen.SETTINGS:
            self._apply_setting(intent)
            return
        # Main menu
        if intent == "resume":
            self._close_menu()
        elif intent == "library":
            self._remove_mode = False
            self._open_library()
        elif intent == "chapters":
            self._open_chapters()
        elif intent == "settings":
            self._open_settings()
        elif intent == "stats":
            self._open_stats()
        elif intent == "about":
            self._open_about()

    # -- "read normally" overlay ----------------------------------------

    def _toggle_reading_view(self) -> None:
        if self.nav.in_menu:
            return
        if self._reading:
            self._close_reading_view()
        else:
            self._open_reading_view()

    def _open_reading_view(self) -> None:
        if not self.engine.total_words:
            return
        self._pause()
        self._reading = True

        # Fill with the original text (paragraph breaks preserved).
        self.reading.config(state="normal")
        self.reading.delete("1.0", "end")
        self.reading.insert("1.0", self._raw_text)
        self.reading.config(state="disabled")

        self._highlight_reading_word()
        self.reading.place(relx=0, rely=0, relwidth=1, relheight=1)
        self.top_bar.lift()  # keep the tip bars visible above the overlay
        self.bottom_bar.lift()
        self.reading.focus_set()
        self._update_status()

    def _close_reading_view(self) -> None:
        self._reading = False
        self.reading.place_forget()
        self.root.focus_set()
        self._render()
        self._update_status()

    def _highlight_reading_word(self) -> None:
        """Tag the current word in the paragraph and scroll it into view."""
        self.reading.tag_remove("current", "1.0", "end")
        i = self.engine.index
        if not (0 <= i < len(self._spans)):
            return
        start, end = self._spans[i]
        start_idx = f"1.0 + {start} chars"
        end_idx = f"1.0 + {end} chars"
        self.reading.tag_add("current", start_idx, end_idx)
        self.reading.see(start_idx)

    def _on_reading_click(self, event: tk.Event) -> str:
        """Clicking a word makes it the point RSVP resumes from."""
        clicked = self.reading.index(f"@{event.x},{event.y}")
        counted = self.reading.count("1.0", clicked, "chars")
        offset = counted[0] if counted else 0
        word_i = self._word_index_at_offset(offset)
        if word_i is not None:
            self.engine.seek_to(word_i)
            self._highlight_reading_word()
        return "break"  # suppress the default text cursor/selection

    def _word_index_at_offset(self, offset: int) -> int | None:
        """Map a character offset in the text to the nearest word index."""
        if not self._span_starts:
            return None
        j = bisect.bisect_right(self._span_starts, offset) - 1
        return max(0, j)

    # -- rendering -------------------------------------------------------

    def _render(self) -> None:
        self._render_content()
        self._update_battery()

    # -- battery indicator ----------------------------------------------

    def _poll_battery(self) -> None:
        self._battery = read_battery()
        self._update_battery()
        # Low power mode reads the battery far less often to save energy.
        interval = _BATT_POLL_MS * (5 if self._low_power else 1)
        self.root.after(interval, self._poll_battery)

    def _update_battery(self) -> None:
        """Show the battery (top-right) on every page, or only on About, per the
        setting; redraw it."""
        show = self._battery_always or self.nav.screen is Screen.ABOUT
        if not show:
            self.battery_canvas.place_forget()
            return
        # On the same line as the top control/status bar, pinned top-right.
        self.battery_canvas.place(relx=1.0, rely=0.07, x=-6, anchor="e")
        # Canvas aliases lift/tkraise to item-raise; use Misc to stack the widget.
        tk.Misc.tkraise(self.battery_canvas)
        self._draw_battery()

    def _draw_battery(self) -> None:
        c = self.battery_canvas
        c.delete("all")
        bx, by, bw, bh = 3, 2, 28, 12           # body rectangle
        _rounded_rect(c, bx, by, bx + bw, by + bh, 3,
                      outline=_BATT_OUTLINE, fill="", width=1)
        c.create_rectangle(bx + bw, by + 4, bx + bw + 2, by + bh - 4,
                           outline="", fill=_BATT_OUTLINE)  # the little terminal
        if self._battery is None:
            c.create_text(bx + bw / 2, by + bh / 2, text="?",
                          font=self._batt_font, fill=_BATT_OUTLINE)
            return
        percent, _charging = self._battery
        fill_w = (bw - 4) * percent / 100
        color = _BATT_OK if percent > 20 else _BATT_LOW
        if fill_w > 0:
            c.create_rectangle(bx + 2, by + 2, bx + 2 + fill_w, by + bh - 2,
                               outline="", fill=color)
        c.create_text(bx + bw / 2, by + bh / 2, text=str(percent),
                      font=self._batt_font, fill="#ffffff")

    # -- power: brightness, low power, auto-off -------------------------

    @staticmethod
    def _next_in(presets: tuple, value: int) -> int:
        """Next value in a cycle (wraps); falls back to the first."""
        try:
            i = presets.index(value)
        except ValueError:
            return presets[0]
        return presets[(i + 1) % len(presets)]

    def _apply_brightness(self) -> None:
        """Dim the display. On the Mac this is window opacity standing in for the
        device backlight; low power mode dims a little further."""
        level = self._brightness / 100.0
        if self._low_power:
            level *= 0.8
        alpha = 0.55 + 0.45 * level   # floor so it never goes near-invisible
        try:
            self.root.attributes("-alpha", alpha)
        except tk.TclError:
            pass

    def _note_activity(self) -> bool:
        """Mark interaction; wake if asleep. Returns True if it consumed a wake."""
        self._last_activity = time.monotonic()
        if self._asleep:
            self._wake()
            return True
        return False

    def _check_auto_off(self) -> None:
        if (self._auto_off_min and not self._asleep and not self.engine.is_playing
                and time.monotonic() - self._last_activity >= self._auto_off_min * 60):
            self._sleep()
        self.root.after(_AUTOOFF_CHECK_MS, self._check_auto_off)

    def _sleep(self) -> None:
        self._asleep = True
        self._pause()
        self.sleep_overlay.place(relx=0, rely=0, relwidth=1, relheight=1)
        tk.Misc.tkraise(self.sleep_overlay)
        self.sleep_overlay.focus_set()

    def _wake(self) -> None:
        if not self._asleep:
            return
        self._asleep = False
        self.sleep_overlay.place_forget()
        self.root.focus_set()
        self._last_activity = time.monotonic()
        self._render()
        self._update_status()

    def _render_content(self) -> None:
        if self.nav.in_menu:
            if self.nav.screen in (Screen.STATS, Screen.ABOUT):
                self._render_info()
            else:
                self._render_menu()
            return
        c = self.canvas
        c.delete("all")
        width = max(c.winfo_width(), 1)
        height = max(c.winfo_height(), 1)
        cy = height / 2
        font = self._word_font

        word = self.engine.current_word
        if not word:
            c.create_text(width / 2, cy, text=self._placeholder, fill=_DIM,
                          font=font, anchor="center")
            return

        if not self._orp_enabled:
            c.create_text(width / 2, cy, text=word, fill=_FG,
                          font=font, anchor="center")
            return

        self._draw_orp(word, width, cy, font)

    def _draw_orp(self, word: str, width: int, cy: float, font: tkfont.Font) -> None:
        """Draw the word with its pivot letter pinned and highlighted."""
        c = self.canvas
        p = pivot_index(word)
        before, pivot, after = word[:p], word[p], word[p + 1:]

        pivot_x = width * _PIVOT_RELX
        pivot_w = font.measure(pivot)
        left_edge = pivot_x - pivot_w / 2
        right_edge = pivot_x + pivot_w / 2

        # Faint guide ticks framing the fixed pivot column.
        font_h = font.metrics("linespace")
        c.create_line(pivot_x, cy - font_h, pivot_x, cy - font_h * 0.55,
                      fill=_GUIDE, width=2)
        c.create_line(pivot_x, cy + font_h * 0.55, pivot_x, cy + font_h,
                      fill=_GUIDE, width=2)

        # The pivot letter stays put; the rest of the word grows around it.
        c.create_text(pivot_x, cy, text=pivot, fill=_PIVOT, font=font, anchor="center")
        if before:
            c.create_text(left_edge, cy, text=before, fill=_FG, font=font, anchor="e")
        if after:
            c.create_text(right_edge, cy, text=after, fill=_FG, font=font, anchor="w")

    # -- menu rendering --------------------------------------------------

    def _menu_layout(self, height: float) -> tuple[int, int, float]:
        """Return ``(top, shown, start_y)`` for the visible window of a menu.

        Lists longer than the screen scroll: only ``shown`` rows are drawn, and
        the window keeps the selected item roughly centred."""
        n = len(self.nav.menu.items)
        max_rows = max(3, int((height * 0.84) // _MENU_ROW_H))
        if n <= max_rows:
            top, shown = 0, n
        else:
            shown = max_rows
            top = max(0, min(self.nav.menu.index - max_rows // 2, n - max_rows))
        start_y = height / 2 - (shown - 1) / 2 * _MENU_ROW_H
        return top, shown, start_y

    def _render_menu(self) -> None:
        c = self.canvas
        c.delete("all")
        width = max(c.winfo_width(), 1)
        height = max(c.winfo_height(), 1)
        menu = self.nav.menu
        n = len(menu.items)
        top, shown, start_y = self._menu_layout(height)
        for row in range(shown):
            i = top + row
            item = menu.items[i]
            y = start_y + row * _MENU_ROW_H
            selected = i == menu.index
            if not item.enabled:
                color = _GUIDE
            elif selected:
                color = _PIVOT
            else:
                color = _FG
            label = f"›  {item.label}" if selected else item.label
            c.create_text(width / 2, y, text=label, fill=color,
                          font=self._menu_font, anchor="center")
        # Scroll hints when there are items off-screen above/below.
        if top > 0:
            c.create_text(width / 2, start_y - _MENU_ROW_H * 0.7, text="▲",
                          fill=_DIM, font=self._status_font, anchor="center")
        if top + shown < n:
            c.create_text(width / 2, start_y + (shown - 1) * _MENU_ROW_H
                          + _MENU_ROW_H * 0.7, text="▼", fill=_DIM,
                          font=self._status_font, anchor="center")

    def _render_info(self) -> None:
        """Draw a Stats/About page: a title, then rows. A row that is a
        ``(label, value)`` pair is laid out as two columns with the colon on a
        fixed centre line so the colons align; a bare string is centred."""
        c = self.canvas
        c.delete("all")
        w = max(c.winfo_width(), 1)
        h = max(c.winfo_height(), 1)
        c.create_text(w / 2, h * 0.15, text=self._info_title, fill=_FG,
                      font=self._menu_font, anchor="center")
        divider = w / 2          # where the colons line up
        gap = 10
        row_h = 23
        start = h * 0.32
        for i, line in enumerate(self._info_lines):
            y = start + i * row_h
            if isinstance(line, tuple):
                label, value = line
                c.create_text(divider - gap, y, text=f"{label}:", fill=_DIM,
                              font=self._info_font, anchor="e")
                c.create_text(divider + gap, y, text=value, fill=_FG,
                              font=self._info_font, anchor="w")
            else:
                c.create_text(w / 2, y, text=line, fill=_FG,
                              font=self._info_font, anchor="center")

    def _menu_index_at_y(self, y: int) -> int | None:
        height = max(self.canvas.winfo_height(), 1)
        top, shown, start_y = self._menu_layout(height)
        row = round((y - start_y) / _MENU_ROW_H)
        if 0 <= row < shown:
            return top + row
        return None

    def _update_status(self) -> None:
        if not self._show_status:
            self.top_bar.config(text="")
            self.bottom_bar.config(text="")
            return
        if self.nav.in_menu:
            if self.nav.screen is Screen.MENU and self._book_name:
                pct = int(self.engine.progress * 100)
                self.top_bar.config(text=f"{self._book_name}    ·    {pct}%")
            else:
                titles = {
                    Screen.LIBRARY: "≡ library",
                    Screen.CHAPTERS: "≡ chapters",
                    Screen.SETTINGS: "≡ settings",
                    Screen.STATS: "≡ stats",
                    Screen.ABOUT: "≡ about",
                }
                self.top_bar.config(text=titles.get(self.nav.screen, "≡ menu"))
            self.bottom_bar.config(text=self._menu_hint)
            return
        if self._reading:
            self.top_bar.config(text="reading view")
            self.bottom_bar.config(
                text="click a word to resume there    ·    tab / esc  back"
            )
            return
        if not self.engine.total_words:
            self.top_bar.config(text="Tap to open the menu  →  Library")
            self.bottom_bar.config(text=_TIPS)
            return
        state = "▶" if self.engine.is_playing else "❚❚"
        pct = int(self.engine.progress * 100)
        name = f"{self._book_name}    " if self._book_name else ""
        # Top line: short status only (battery sits beside it). Tips on the bottom.
        self.top_bar.config(text=f"{name}{state}  {self.engine.wpm} wpm   {pct}%")
        self.bottom_bar.config(text=_TIPS)

    # -- lifecycle -------------------------------------------------------

    def run(self) -> None:
        self.root.mainloop()


def run(book_path: str | Path | None = None) -> None:
    RsvpApp(book_path).run()
