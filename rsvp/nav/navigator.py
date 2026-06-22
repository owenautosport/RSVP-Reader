"""The screen state machine.

Tracks which screen is showing and, when in a menu, owns the menu cursor. It
does not execute intents (open the library, change a setting) — it returns the
selected item's id and lets the app do that, so this stays toolkit- and
feature-agnostic.

Phase 1 has just two screens (READING and MENU). Library / Settings / Chapters
etc. become additional screens as they are built, without changing this shape.
"""

from __future__ import annotations

from enum import Enum, auto

from .menu import Menu


class Screen(Enum):
    READING = auto()
    MENU = auto()


class Navigator:
    def __init__(self, menu: Menu) -> None:
        self._screen = Screen.READING
        self.menu = menu

    @property
    def screen(self) -> Screen:
        return self._screen

    @property
    def in_menu(self) -> bool:
        return self._screen == Screen.MENU

    def open_menu(self) -> None:
        self._screen = Screen.MENU
        self.menu.reset()

    def close_menu(self) -> None:
        self._screen = Screen.READING

    def move(self, delta: int) -> None:
        if self.in_menu:
            self.menu.move(delta)

    def select(self) -> str | None:
        """Return the id of the highlighted item (None if disabled/empty)."""
        if not self.in_menu:
            return None
        item = self.menu.current
        return item.id if item and item.enabled else None
