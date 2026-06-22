"""Toolkit-agnostic navigation: input abstraction, menu model, and the screen
state machine.

Nothing here imports a GUI toolkit. The Mac front-end translates keyboard and
mouse into these raw inputs today; the pocket device will translate its 3 top
buttons and touchscreen into the very same inputs later, so the menu/navigation
logic ports unchanged.
"""

from .actions import Button, Swipe
from .menu import MenuItem, Menu
from .navigator import Screen, Navigator

__all__ = ["Button", "Swipe", "MenuItem", "Menu", "Screen", "Navigator"]
