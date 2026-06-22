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
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, font as tkfont

from ..books import BookLoadError, SUPPORTED_EXTENSIONS, find_books, load_book
from ..core import (
    RsvpEngine,
    find_chapters,
    paragraph_end_indices,
    pivot_index,
    tokenize,
    token_spans,
)
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
    MenuItem("settings", "Settings", enabled=False),
    MenuItem("stats", "Stats", enabled=False),
    MenuItem("about", "About", enabled=False),
]

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
_TIPS_TOP = "space play/pause    ↑/↓ speed    ←/→ word    [ ] sentence    tab read"
_TIPS_BOTTOM = "f font    p pivot    r restart    o open    h hide    q quit"


class RsvpApp:
    def __init__(self, book_path: str | Path | None = None) -> None:
        self.engine = RsvpEngine()
        self.store = Store()
        self.nav = Navigator({
            Screen.MENU: Menu(_MENU_ITEMS),
            Screen.LIBRARY: Menu([]),   # filled when the Library is opened
            Screen.CHAPTERS: Menu([]),  # filled when Chapters is opened
        })
        self._after_id: str | None = None
        self._words_since_save = 0
        self._furthest = 0  # furthest word reached; what we resume to (re-reading won't lower it)
        self._show_status = True
        self._reading = False          # is the "read normally" overlay open?
        self._placeholder = "—"
        self._book_name = ""
        self._book_path: Path | None = None  # current book, for saving position
        self._menu_hint = ""
        self._press: tuple[int, int] | None = None  # gesture start point
        self._raw_text = ""            # original text, for the reading overlay
        self._span_starts: list[int] = []  # start offset of each word (for clicks)
        self._spans: list[tuple[int, int]] = []

        # Restore saved settings (speed, font, pivot) or fall back to defaults.
        s = self.store.get_settings(
            {"wpm": self.engine.wpm, "font_index": 0, "orp": True}
        )
        self.engine.wpm = int(s["wpm"])
        self._font_idx = int(s["font_index"]) % len(_WORD_FONTS)
        self._orp_enabled = bool(s["orp"])

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
        r.bind("<Right>", lambda e: self._step(+1))
        r.bind("<Left>", lambda e: self._step(-1))
        r.bind("<bracketleft>", lambda e: self._rewind_sentence())
        r.bind("<bracketright>", lambda e: self._forward_sentence())
        r.bind("<r>", lambda e: self._restart())
        r.bind("<o>", lambda e: self._open_dialog())
        r.bind("<p>", lambda e: self._toggle_orp())
        r.bind("<f>", lambda e: self._cycle_font())
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
        else:
            if swipe is Swipe.LEFT:
                self._rewind_sentence()
            elif swipe is Swipe.RIGHT:
                self._forward_sentence()

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

    def _open_dialog(self) -> None:
        was_playing = self.engine.is_playing
        self._pause()
        patterns = " ".join(f"*{ext}" for ext in SUPPORTED_EXTENSIONS)
        path = filedialog.askopenfilename(
            title="Open book",
            filetypes=[("Text books", patterns), ("All files", "*.*")],
        )
        if path:
            self._open_path(Path(path))
        elif was_playing:
            self._play()

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
        self._render()
        self._update_status()

    # -- persistence -----------------------------------------------------

    def _save_position(self) -> None:
        self._words_since_save = 0
        if self._book_path is not None and self.engine.total_words:
            # Resume to the furthest point reached, not wherever the cursor is
            # now — so going back to re-read never loses your place.
            self._furthest = max(self._furthest, self.engine.index)
            self.store.set_position(self._book_path, self._furthest)
            self.store.save()

    def _save_settings(self) -> None:
        self.store.set_settings({
            "wpm": self.engine.wpm,
            "font_index": self._font_idx,
            "orp": self._orp_enabled,
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
        self._cancel_pending()
        self._tick()
        self._update_status()

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

    # -- manual navigation & speed --------------------------------------

    def _step(self, delta: int) -> None:
        if self._controls_locked():
            return
        self._pause()
        self.engine.seek_to(self.engine.index + delta)
        self._render()
        self._update_status()

    def _rewind_sentence(self) -> None:
        """Re-read: jump back to the start of the current/previous sentence."""
        if self._controls_locked():
            return
        self._pause()
        self.engine.rewind_sentence()
        self._render()
        self._update_status()

    def _forward_sentence(self) -> None:
        if self._controls_locked():
            return
        self._pause()
        self.engine.forward_sentence()
        self._render()
        self._update_status()

    def _restart(self) -> None:
        if self._controls_locked():
            return
        self._pause()
        self.engine.restart()
        self._render()
        self._update_status()

    def _cycle_font(self) -> None:
        if self._controls_locked():
            return
        self._font_idx = (self._font_idx + 1) % len(_WORD_FONTS)
        self._word_font.config(family=_WORD_FONTS[self._font_idx])
        self._save_settings()
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

    def _toggle_orp(self) -> None:
        if self._controls_locked():
            return
        self._orp_enabled = not self._orp_enabled
        self._save_settings()
        self._render()

    # -- main menu -------------------------------------------------------

    def _toggle_menu(self) -> None:
        if self._reading:
            return
        self._close_menu() if self.nav.in_menu else self._open_menu()

    def _open_menu(self) -> None:
        if not self.engine.total_words:
            return
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

    def _open_library(self) -> None:
        dirs = [_SAMPLES_DIR, _USER_BOOKS_DIR]
        if self._book_path is not None:
            dirs.append(self._book_path.parent)
        books = find_books(dirs)
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

    def _menu_move(self, delta: int) -> None:
        self.nav.move(delta)
        self._render()

    def _menu_select(self) -> None:
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
        # Main menu
        if intent == "resume":
            self._close_menu()
        elif intent == "library":
            self._open_library()
        elif intent == "chapters":
            self._open_chapters()
        else:  # not built yet — show the roadmap honestly
            self._menu_hint = f"{intent.title()} — coming soon"
            self._update_status()

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
        if self.nav.in_menu:
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
                titles = {Screen.LIBRARY: "≡ library", Screen.CHAPTERS: "≡ chapters"}
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
            self.top_bar.config(text="Press  o  to open a book")
            self.bottom_bar.config(text=_TIPS_BOTTOM)
            return
        state = "▶" if self.engine.is_playing else "❚❚"
        pct = int(self.engine.progress * 100)
        name = f"{self._book_name}    " if self._book_name else ""
        font = _WORD_FONTS[self._font_idx]
        # Top bar: live status + primary tips. Bottom bar: the rest.
        self.top_bar.config(
            text=f"{name}{state}  {self.engine.wpm} wpm   {pct}%   ·   {font}        {_TIPS_TOP}"
        )
        self.bottom_bar.config(text=_TIPS_BOTTOM)

    # -- lifecycle -------------------------------------------------------

    def run(self) -> None:
        self.root.mainloop()


def run(book_path: str | Path | None = None) -> None:
    RsvpApp(book_path).run()
