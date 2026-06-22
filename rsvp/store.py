"""Local-only persistence: remember the reading position per book and the global
settings, so the reader resumes exactly where you left off.

Plain JSON in a single file under the user's home directory. No network, no
accounts — just a small file on local storage (the same role device flash will
play later). Writes are atomic (temp file + replace) so a crash mid-save can't
corrupt the state.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

DEFAULT_PATH = Path.home() / ".rsvp-reader" / "state.json"


def book_key(path: str | Path) -> str:
    """A stable key for a book file (its resolved absolute path)."""
    return str(Path(path).resolve())


class Store:
    def __init__(self, path: str | Path = DEFAULT_PATH) -> None:
        self._path = Path(path)
        self._data: dict = {"settings": {}, "books": {}}
        self._load()

    def _load(self) -> None:
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except (FileNotFoundError, ValueError, OSError):
            return
        if isinstance(raw, dict):
            self._data["settings"] = dict(raw.get("settings", {}))
            self._data["books"] = dict(raw.get("books", {}))

    def save(self) -> None:
        """Write current state to disk atomically. Never raises on IO error."""
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self._data, indent=2), encoding="utf-8")
            os.replace(tmp, self._path)
        except OSError:
            pass  # persistence is best-effort; never break reading over it

    # -- settings --------------------------------------------------------

    def get_settings(self, defaults: dict) -> dict:
        merged = dict(defaults)
        merged.update(self._data.get("settings", {}))
        return merged

    def set_settings(self, settings: dict) -> None:
        self._data["settings"] = dict(settings)

    # -- per-book reading position --------------------------------------

    def _entry(self, path: str | Path) -> dict:
        return self._data.setdefault("books", {}).setdefault(book_key(path), {})

    def get_position(self, path: str | Path) -> int:
        entry = self._data.get("books", {}).get(book_key(path))
        if isinstance(entry, dict):
            try:
                return max(0, int(entry.get("index", 0)))
            except (TypeError, ValueError):
                return 0
        return 0

    def set_position(self, path: str | Path, index: int) -> None:
        self._entry(path)["index"] = int(index)

    def get_seconds(self, path: str | Path) -> float:
        entry = self._data.get("books", {}).get(book_key(path))
        if isinstance(entry, dict):
            try:
                return max(0.0, float(entry.get("seconds", 0)))
            except (TypeError, ValueError):
                return 0.0
        return 0.0

    def set_seconds(self, path: str | Path, seconds: float) -> None:
        self._entry(path)["seconds"] = float(seconds)
