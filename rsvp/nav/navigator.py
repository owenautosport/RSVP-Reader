"""The screen state machine.

A small stack of screens. READING is always the base; menus/lists are pushed on
top and popped with Back, so nesting (Reading → Menu → Library) needs no special
cases. Each list screen is backed by a ``Menu``. The navigator never executes an
intent (open the library, change a setting) — it returns the selected item's id
and lets the app act, so this stays toolkit- and feature-agnostic.
"""

from __future__ import annotations

from enum import Enum, auto

from .menu import Menu


class Screen(Enum):
    READING = auto()
    MENU = auto()
    LIBRARY = auto()
    CHAPTERS = auto()
    SETTINGS = auto()
    STATS = auto()
    ABOUT = auto()


class Navigator:
    def __init__(self, menus: dict[Screen, Menu]) -> None:
        # Menus for the list screens (everything except READING).
        self._menus = dict(menus)
        self._stack: list[Screen] = [Screen.READING]

    @property
    def screen(self) -> Screen:
        return self._stack[-1]

    @property
    def in_menu(self) -> bool:
        """True on any non-reading (list) screen — used to lock reading input."""
        return self.screen is not Screen.READING

    @property
    def menu(self) -> Menu | None:
        """The Menu backing the current screen (None on READING)."""
        return self._menus.get(self.screen)

    def open(self, screen: Screen, items: list | None = None) -> None:
        """Show a list screen, optionally replacing its items first.

        Pushes it onto the stack, unless it is already the current screen — then
        it just refreshes in place (so re-opening to refresh doesn't stack
        duplicate screens and bloat the back history)."""
        menu = self._menus.get(screen)
        if menu is None:
            return
        if items is not None:
            menu.set_items(items)
        menu.reset()
        if self.screen is not screen:
            self._stack.append(screen)

    def back(self) -> None:
        """Pop one screen (no-op at the base reading screen)."""
        if len(self._stack) > 1:
            self._stack.pop()

    def go_reading(self) -> None:
        """Collapse straight back to the reading screen."""
        self._stack = [Screen.READING]

    def move(self, delta: int) -> None:
        menu = self.menu
        if menu is not None:
            menu.move(delta)

    def select(self) -> str | None:
        """Return the id of the highlighted item (None if disabled/empty)."""
        menu = self.menu
        if menu is None:
            return None
        item = menu.current
        return item.id if item and item.enabled else None
