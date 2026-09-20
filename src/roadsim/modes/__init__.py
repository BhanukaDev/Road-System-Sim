"""Mode registry. One line per way of using the world.

Order is the hotkey order: Shift+1, Shift+2, ... Plain digits belong to the active
mode's tools, so the two never collide.
"""

from .base import Mode, ModeBox
from .road import RoadMode
from .view import ViewMode

MODES: list[type[Mode]] = [ViewMode, RoadMode]
"""The first entry is where the app starts: looking before touching."""

DEFAULT_MODE = ViewMode.name

__all__ = ["DEFAULT_MODE", "MODES", "Mode", "ModeBox", "RoadMode", "ViewMode"]
