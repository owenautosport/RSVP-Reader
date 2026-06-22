"""The minimal tkinter window that drives the RSVP engine.

Layout is deliberately almost-empty: one large word, centered, on a dark
background, with a faint status/help line that can be hidden. The window owns
the real timer; on each word it asks the engine how long to wait, schedules a
single ``after`` callback, and advances.
"""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, font as tkfont

from ..books import BookLoadError, SUPPORTED_EXTENSIONS, load_book
from ..core import RsvpEngine, tokenize

# Quiet, low-contrast palette so the word is the only thing that stands out.
_BG = "#111111"
_FG = "#f2f2f2"
_DIM = "#666666"

_WPM_STEP = 25
_HELP = "space play/pause   ←/→ step   ↑/↓ speed   r restart   o open   h hide   q quit"


class RsvpApp:
    def __init__(self, book_path: str | Path | None = None) -> None:
        self.engine = RsvpEngine()
        self._after_id: str | None = None
        self._show_status = True
        self._book_name = ""

        self.root = tk.Tk()
        self.root.title("RSVP Pocket E-Reader")
        self.root.configure(bg=_BG)
        self.root.geometry("900x500")
        self.root.minsize(420, 240)

        self._word_font = tkfont.Font(family="Helvetica", size=72, weight="bold")
        self._status_font = tkfont.Font(family="Helvetica", size=13)

        self.word_label = tk.Label(
            self.root, text="", font=self._word_font, fg=_FG, bg=_BG, anchor="center"
        )
        self.word_label.place(relx=0.5, rely=0.5, anchor="center")

        self.status_label = tk.Label(
            self.root, text="", font=self._status_font, fg=_DIM, bg=_BG, anchor="center"
        )
        self.status_label.place(relx=0.5, rely=0.93, anchor="center")

        self._bind_keys()

        if book_path is not None:
            self._open_path(Path(book_path))
        else:
            self._render()
            self._update_status()

    # -- setup -----------------------------------------------------------

    def _bind_keys(self) -> None:
        r = self.root
        r.bind("<space>", lambda e: self._toggle())
        r.bind("<Up>", lambda e: self._change_speed(+_WPM_STEP))
        r.bind("<Down>", lambda e: self._change_speed(-_WPM_STEP))
        r.bind("<Right>", lambda e: self._step(+1))
        r.bind("<Left>", lambda e: self._step(-1))
        r.bind("<r>", lambda e: self._restart())
        r.bind("<o>", lambda e: self._open_dialog())
        r.bind("<h>", lambda e: self._toggle_status())
        r.bind("<q>", lambda e: self.root.destroy())
        r.bind("<Escape>", lambda e: self.root.destroy())

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
        try:
            text = load_book(path)
        except BookLoadError as exc:
            self._book_name = ""
            self.engine.load([])
            self.word_label.config(text="⚠")
            self.status_label.config(text=str(exc))
            return
        self.engine.load(tokenize(text))
        self._book_name = path.stem
        self._render()
        self._update_status()

    # -- playback control ------------------------------------------------

    def _toggle(self) -> None:
        if self.engine.is_playing:
            self._pause()
        else:
            self._play()

    def _play(self) -> None:
        if not self.engine.total_words:
            return
        self.engine.play()
        self._cancel_pending()
        self._tick()
        self._update_status()

    def _pause(self) -> None:
        self.engine.pause()
        self._cancel_pending()
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
            self._tick()
        else:  # reached the last word
            self.engine.pause()
            self._render()
            self._update_status()

    def _cancel_pending(self) -> None:
        if self._after_id is not None:
            self.root.after_cancel(self._after_id)
            self._after_id = None

    # -- manual navigation & speed --------------------------------------

    def _step(self, delta: int) -> None:
        self._pause()
        self.engine.seek_to(self.engine.index + delta)
        self._render()
        self._update_status()

    def _restart(self) -> None:
        self._pause()
        self.engine.restart()
        self._render()
        self._update_status()

    def _change_speed(self, delta: int) -> None:
        self.engine.adjust_wpm(delta)
        self._update_status()

    def _toggle_status(self) -> None:
        self._show_status = not self._show_status
        self._update_status()

    # -- rendering -------------------------------------------------------

    def _render(self) -> None:
        word = self.engine.current_word
        self.word_label.config(text=word if word else "—")

    def _update_status(self) -> None:
        if not self._show_status:
            self.status_label.config(text="")
            return
        if not self.engine.total_words:
            self.status_label.config(text="Press  o  to open a book")
            return
        state = "▶" if self.engine.is_playing else "❚❚"
        pct = int(self.engine.progress * 100)
        name = f"{self._book_name}   " if self._book_name else ""
        self.status_label.config(
            text=f"{name}{state}  {self.engine.wpm} wpm   {pct}%   ·   {_HELP}"
        )

    # -- lifecycle -------------------------------------------------------

    def run(self) -> None:
        self.root.mainloop()


def run(book_path: str | Path | None = None) -> None:
    RsvpApp(book_path).run()
