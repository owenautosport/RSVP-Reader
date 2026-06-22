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
import time
import tkinter as tk
from pathlib import Path
from tkinter import font as tkfont

from ..books import BookLoadError, find_books, load_book
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
_BATT_OK = "#34c759"
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

# Where the bundled sample book lives (repo root / samples), used by the Library.
_SAMPLES_DIR = Path(__file__).resolve().parents[2] / "samples"
# A user drop-folder for their own books.
_USER_BOOKS_DIR = Path.home() / ".rsvp-reader" / "books"
_MENU_ROW_H = 46  # pixel height of a menu row (also used for tap hit-testing)

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

# Word fonts the reader can cycle through with 'f' (a sans, two serifs, a mono,
# and a wide sans). Missing families fall back to a system default automatically.
_WORD_FONTS = ("Helvetica", "Georgia", "Menlo", "Verdana", "Palatino")

_WPM_STEP = 25
# Control tips framing the word: primary actions on top, the rest on the bottom.
_TIPS_TOP = "space play/pause    ↑/↓ speed    m menu    tab read"
_TIPS_BOTTOM = "r restart    h hide    q quit"


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

        # Restore saved settings (speed, font, pivot, battery) or defaults.
        s = self.store.get_settings(
            {"wpm": self.engine.wpm, "font_index": 0, "orp": True,
             "battery_always": True}
        )
        self.engine.wpm = int(s["wpm"])
        self._font_idx = int(s["font_index"]) % len(_WORD_FONTS)
        self._orp_enabled = bool(s["orp"])
        self._battery_always = bool(s["battery_always"])  # show on all pages vs About only
        self._battery: tuple[int, bool] | None = None

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
            self.root, width=44, height=20, bg=_BG, highlightthickness=0
        )

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

        self._poll_battery()  # first read + schedule periodic refresh

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
            text = load_book(path)
        except BookLoadError as exc:
            self._book_name = ""
            self._book_path = None
            self.engine.load([])
            self._raw_text = ""
            self._spans = []
            self._span_starts = []
            self._placeholder = "⚠"
            self._render()
            self.top_bar.config(text=str(exc))
            self.bottom_bar.config(text=_TIPS_BOTTOM)
            return
        self._placeholder = "—"
        self._raw_text = text
        self._spans = token_spans(text)
        self._span_starts = [s for s, _ in self._spans]
        resume_at = self.store.get_position(path)  # 0 if never opened before
        self.engine.load(
            tokenize(text),
            start_index=resume_at,
            paragraph_ends=paragraph_end_indices(text),
        )
        self._book_path = path
        self._book_name = path.stem
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
        if books:
            items = []
            for i, p in enumerate(books):
                if current is not None and book_key(p) == current:
                    current_idx = i  # cursor starts here; no separate marker
                items.append(MenuItem(str(p), p.stem))
            self._menu_hint = "tap a book to open    ·    swipe ▶ / esc  back"
        else:
            items = [MenuItem("", "No books found", enabled=False)]
            self._menu_hint = f"drop .txt books in {_USER_BOOKS_DIR}"
        self.nav.open(Screen.LIBRARY, items=items)
        if current_idx is not None:
            self.nav.menu.select_index(current_idx)  # start on the open book
        self._render()
        self._update_status()

    def _chapter_targets(self) -> list[tuple[str, int]]:
        """(label, word-index) jump points: real chapters if detected, else
        evenly-spaced progress markers."""
        total = self.engine.total_words
        if not total:
            return []
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
            MenuItem("set_battery", f"Battery:  {battery}"),
        ]

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
        lines = [
            "A quiet, single-purpose speed reader.",
            "Fully offline — no accounts, no network.",
            "",
            ("Version", __version__),
            ("Library", f"{n} book{'' if n == 1 else 's'}"),
            ("Storage", self._format_bytes(used)),
        ]
        self._show_info(Screen.ABOUT, "RSVP Pocket E-Reader", lines)

    @staticmethod
    def _safe_size(path: Path) -> int:
        try:
            return path.stat().st_size
        except OSError:
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
        self.root.after(_BATT_POLL_MS, self._poll_battery)

    def _update_battery(self) -> None:
        """Show the battery (top-right) on every page, or only on About, per the
        setting; redraw it."""
        show = self._battery_always or self.nav.screen is Screen.ABOUT
        if not show:
            self.battery_canvas.place_forget()
            return
        self.battery_canvas.place(relx=1.0, x=-6, y=4, anchor="ne")
        # Canvas aliases lift/tkraise to item-raise; use Misc to stack the widget.
        tk.Misc.tkraise(self.battery_canvas)
        self._draw_battery()

    def _draw_battery(self) -> None:
        c = self.battery_canvas
        c.delete("all")
        bx, by, bw, bh = 3, 3, 28, 13           # body rectangle
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

    def _menu_start_y(self, height: float) -> float:
        n = len(self.nav.menu.items)
        return height / 2 - (n - 1) / 2 * _MENU_ROW_H

    def _render_menu(self) -> None:
        c = self.canvas
        c.delete("all")
        width = max(c.winfo_width(), 1)
        height = max(c.winfo_height(), 1)
        start_y = self._menu_start_y(height)
        menu = self.nav.menu
        for i, item in enumerate(menu.items):
            y = start_y + i * _MENU_ROW_H
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
        start_y = self._menu_start_y(height)
        i = round((y - start_y) / _MENU_ROW_H)
        if 0 <= i < len(self.nav.menu.items):
            return i
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
            self.bottom_bar.config(text=_TIPS_BOTTOM)
            return
        state = "▶" if self.engine.is_playing else "❚❚"
        pct = int(self.engine.progress * 100)
        name = f"{self._book_name}    " if self._book_name else ""
        # Top bar: live status + primary tips. Bottom bar: the rest.
        self.top_bar.config(
            text=f"{name}{state}  {self.engine.wpm} wpm   {pct}%        {_TIPS_TOP}"
        )
        self.bottom_bar.config(text=_TIPS_BOTTOM)

    # -- lifecycle -------------------------------------------------------

    def run(self) -> None:
        self.root.mainloop()


def run(book_path: str | Path | None = None) -> None:
    RsvpApp(book_path).run()
