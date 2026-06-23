"""The user-facing side of self-update: a small styled dialog that announces a
new version, shows the release notes, and — on consent — downloads and applies
it with a progress bar. All network/IO runs on a worker thread; UI updates are
marshalled back with ``root.after`` so the reading loop is never blocked.
"""

from __future__ import annotations

import queue
import threading
import tkinter as tk
import webbrowser
from tkinter import ttk

from ..update.updater import NoAssetError

# Match the app's quiet dark palette.
_BG = "#111111"
_FG = "#f2f2f2"
_DIM = "#888888"
_ACCENT = "#e8643c"
_NOTE_BG = "#1a1a1a"


def _center(win: tk.Toplevel, parent: tk.Misc) -> None:
    win.update_idletasks()
    try:
        px, py = parent.winfo_rootx(), parent.winfo_rooty()
        pw, ph = parent.winfo_width(), parent.winfo_height()
        w, h = win.winfo_width(), win.winfo_height()
        win.geometry(f"+{px + (pw - w) // 2}+{py + (ph - h) // 3}")
    except tk.TclError:
        pass


def show_message(parent: tk.Misc, title: str, body: str) -> None:
    """A small styled OK dialog, used for 'up to date' / 'offline' feedback."""
    win = tk.Toplevel(parent, bg=_BG)
    win.title(title)
    win.resizable(False, False)
    win.transient(parent)
    tk.Label(win, text=title, fg=_FG, bg=_BG,
             font=("Helvetica", 15, "bold")).pack(padx=28, pady=(22, 8))
    tk.Label(win, text=body, fg=_DIM, bg=_BG, font=("Helvetica", 12),
             justify="center", wraplength=320).pack(padx=28, pady=(0, 18))
    tk.Button(win, text="OK", command=win.destroy, relief="flat",
              bg=_NOTE_BG, fg=_FG, activebackground=_ACCENT,
              activeforeground=_FG, padx=18, pady=4, highlightthickness=0,
              bd=0).pack(pady=(0, 20))
    _center(win, parent)
    win.bind("<Escape>", lambda e: win.destroy())
    win.bind("<Return>", lambda e: win.destroy())


class UpdateDialog:
    """Announce ``release`` and drive the download/apply on the user's consent."""

    def __init__(self, root: tk.Misc, updater, current_version: str, release,
                 can_apply: bool, on_apply=None) -> None:
        self.root = root
        self.updater = updater
        self.release = release
        self.can_apply = can_apply
        self._on_apply = on_apply  # persist reading state before we hand off

        win = self.win = tk.Toplevel(root, bg=_BG)
        win.title("Update available")
        win.transient(root)
        win.resizable(False, False)
        win.bind("<Escape>", lambda e: self._later())

        tk.Label(win, text="Update available", fg=_FG, bg=_BG,
                 font=("Helvetica", 16, "bold")).pack(padx=28, pady=(22, 2))
        tk.Label(win, text=f"{current_version}  →  {self._clean(release.version)}",
                 fg=_ACCENT, bg=_BG, font=("Helvetica", 13, "bold")).pack(pady=(0, 12))

        notes = tk.Text(win, width=52, height=10, wrap="word", bg=_NOTE_BG,
                        fg=_DIM, relief="flat", highlightthickness=0,
                        padx=14, pady=12, font=("Helvetica", 11))
        notes.insert("1.0", release.notes.strip() or "No release notes provided.")
        notes.configure(state="disabled")
        notes.pack(padx=28)

        # Progress bar (hidden until an update starts).
        self._status = tk.Label(win, text="", fg=_DIM, bg=_BG, font=("Helvetica", 11))
        self._bar = ttk.Progressbar(win, mode="determinate", length=360, maximum=100)

        self._buttons = tk.Frame(win, bg=_BG)
        self._buttons.pack(padx=28, pady=18, fill="x")
        primary_text = "Update & Restart" if can_apply else "Open Releases page"
        primary_cmd = self._start if can_apply else self._open_page
        self._primary = tk.Button(
            self._buttons, text=primary_text, command=primary_cmd, relief="flat",
            bg=_ACCENT, fg=_FG, activebackground=_ACCENT, activeforeground=_FG,
            padx=16, pady=5, highlightthickness=0, bd=0)
        self._primary.pack(side="right")
        self._later_btn = tk.Button(
            self._buttons, text="Later", command=self._later, relief="flat",
            bg=_NOTE_BG, fg=_DIM, activebackground=_NOTE_BG, activeforeground=_FG,
            padx=16, pady=5, highlightthickness=0, bd=0)
        self._later_btn.pack(side="right", padx=(0, 10))

        _center(win, root)
        try:
            win.grab_set()  # modal: keep focus on the choice
        except tk.TclError:
            pass

    @staticmethod
    def _clean(version: str) -> str:
        return version.lstrip("vV")

    # -- actions ---------------------------------------------------------

    def _later(self) -> None:
        self._close()

    def _open_page(self) -> None:
        if self.release.html_url:
            webbrowser.open(self.release.html_url)
        self._close()

    def _start(self) -> None:
        if self._on_apply:
            self._on_apply()  # save reading position/settings before restart
        self._primary.configure(state="disabled")
        self._later_btn.configure(state="disabled")
        self._status.configure(text="Downloading…")
        self._status.pack(pady=(0, 4))
        self._bar.pack(padx=28, pady=(0, 8))
        # The worker thread only ever puts messages on this queue; a main-thread
        # poller drains it and touches the widgets. Tkinter is not thread-safe,
        # so no Tk call is ever made off the main thread.
        self._queue = queue.Queue()
        threading.Thread(target=self._worker, daemon=True).start()
        self._poll_queue()

    def _worker(self) -> None:
        try:
            self.updater.download_and_apply(self.release, progress=self._on_progress)
            # On a real frozen build the applier relaunches and we never get
            # here. If we do (e.g. it returned), just close.
            self._queue.put(("close",))
        except NoAssetError:
            self._queue.put(("fail", "No installer is available for your system."))
        except Exception:
            self._queue.put(("fail", "The update couldn't be applied."))

    def _on_progress(self, done: int, total: int) -> None:
        # Runs on the worker thread — only enqueue, never touch Tk here.
        pct = int(done / total * 100) if total else 0
        self._queue.put(("progress", pct))

    def _poll_queue(self) -> None:
        try:
            while True:
                msg = self._queue.get_nowait()
                kind = msg[0]
                if kind == "progress":
                    self._set_progress(msg[1])
                elif kind == "fail":
                    self._fail(msg[1])
                    return  # stop polling; user decides next step
                elif kind == "close":
                    self._close()
                    return
        except queue.Empty:
            pass
        if self.win.winfo_exists():
            self.win.after(80, self._poll_queue)

    def _set_progress(self, pct: int) -> None:
        self._bar.configure(value=pct)
        label = "Installing…" if pct >= 100 else f"Downloading…  {pct}%"
        self._status.configure(text=label)

    def _fail(self, message: str) -> None:
        self._bar.pack_forget()
        self._status.configure(text=message + "\nYou can download it manually instead.")
        self._primary.configure(text="Open Releases page", command=self._open_page,
                                state="normal")
        self._later_btn.configure(state="normal")

    def _close(self) -> None:
        try:
            self.win.grab_release()
        except tk.TclError:
            pass
        self.win.destroy()
