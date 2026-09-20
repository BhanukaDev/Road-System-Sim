"""The interface as a whole: an ordered list of widgets over the world.

Two rules earn this file its place.

**Chrome consumes everything over it, wheel included.** Scrolling the road bar
must not zoom the map underneath it, and a click on a button must not also place a
road point. That is what `wants` is for, and the scene asks it *before* updating
the cursor - otherwise a tool would happily preview a road behind the bar.

**Events reach the front first.** Widgets draw back to front, so they are asked
front to back. With bars stacked along one edge that ordering is what makes the top
one win rather than whichever happens to be first in the list.
"""

from __future__ import annotations

import pygame

from .theme import THEME, Theme
from .widget import Widget

BLOCKED_EVENTS = (
    pygame.MOUSEBUTTONDOWN,
    pygame.MOUSEBUTTONUP,
    pygame.MOUSEWHEEL,
)
"""Event kinds the world must never see while the cursor is over chrome."""


class UiScreen:
    def __init__(self, widgets: list[Widget] | None = None, theme: Theme = THEME) -> None:
        self.widgets: list[Widget] = widgets or []
        self.theme = theme
        self.cursor: tuple[int, int] | None = None
        self._viewport = pygame.Rect(0, 0, 0, 0)

    def set_widgets(self, widgets: list[Widget]) -> None:
        """Swap the whole set - what a mode change does."""
        self.widgets = widgets
        if self._viewport.width:
            self.layout(self._viewport.size)

    def layout(self, viewport: tuple[int, int]) -> None:
        self._viewport = pygame.Rect(0, 0, *viewport)
        for widget in self.widgets:
            widget.layout(self._viewport)

    # -- input -------------------------------------------------------------

    def wants(self, pos: tuple[int, int] | None) -> bool:
        """Is the cursor over chrome? The scene's cue to leave the world alone."""
        if pos is None:
            return False
        return any(w.enabled and w.contains(pos) for w in self.widgets)

    def handle_event(self, event: pygame.event.Event) -> bool:
        if event.type == pygame.MOUSEMOTION:
            self.cursor = event.pos
            for widget in reversed(self.widgets):
                widget.set_hover(event.pos)
            return self.wants(event.pos)

        for widget in reversed(self.widgets):
            if widget.enabled and widget.handle_event(event):
                return True

        # Nothing claimed it, but chrome still shields the world from it.
        if event.type in BLOCKED_EVENTS:
            pos = getattr(event, "pos", self.cursor)
            return self.wants(pos)
        return False

    # -- drawing -----------------------------------------------------------

    def draw(self, surface: pygame.Surface) -> None:
        for widget in self.widgets:
            if widget.enabled:
                widget.draw(surface, self.theme)
