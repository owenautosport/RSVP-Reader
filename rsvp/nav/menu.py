"""A minimal vertical-list menu model: items, a selection cursor, movement.

Pure data + cursor logic, no rendering. The front-end draws it and turns taps
into a selected index; this just tracks state and answers "what is selected".
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MenuItem:
    id: str          # stable intent id the app acts on (e.g. "library")
    label: str       # what the user sees
    enabled: bool = True  # dimmed / not selectable when False


class Menu:
    def __init__(self, items: list[MenuItem]) -> None:
        self._items = list(items)
        self._index = 0

    @property
    def items(self) -> list[MenuItem]:
        return self._items

    def set_items(self, items: list[MenuItem]) -> None:
        """Replace the items (e.g. a freshly scanned book list) and reset."""
        self._items = list(items)
        self._index = 0

    @property
    def index(self) -> int:
        return self._index

    @property
    def current(self) -> MenuItem | None:
        return self._items[self._index] if self._items else None

    def reset(self) -> None:
        """Put the cursor on the first selectable item."""
        self._index = 0
        if self._items and not self._items[0].enabled:
            self.move(1)

    def move(self, delta: int) -> None:
        """Move the cursor by ``delta``, skipping disabled items, clamped."""
        if not self._items:
            return
        i = self._index
        step = 1 if delta > 0 else -1
        for _ in range(abs(delta)):
            j = i
            while 0 <= j + step < len(self._items):
                j += step
                if self._items[j].enabled:
                    i = j
                    break
        self._index = i

    def select_index(self, index: int) -> None:
        """Point the cursor at ``index`` if it exists and is enabled."""
        if 0 <= index < len(self._items) and self._items[index].enabled:
            self._index = index
