"""The widget contract.

Small on purpose. A widget knows its rectangle, whether the cursor is over it,
and how to draw itself; it reports whether it consumed an event. It does not know
about the network, the camera or the editor - the callbacks it is handed do.

That is what keeps `ui` a layer rather than a second copy of the editor: a button
is a rectangle plus a function, and the function comes from whoever built it.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

import pygame

from .theme import Theme


class Widget(ABC):
    def __init__(self, rect: pygame.Rect | None = None) -> None:
        self.rect = pygame.Rect(0, 0, 0, 0) if rect is None else pygame.Rect(rect)
        self.hovered = False
        self.enabled = True

    # -- layout ------------------------------------------------------------

    def layout(self, rect: pygame.Rect) -> None:
        """Take the space you are given. Containers override to divide it up."""
        self.rect = pygame.Rect(rect)

    def contains(self, pos: tuple[int, int]) -> bool:
        return self.rect.collidepoint(pos)

    # -- input -------------------------------------------------------------

    def set_hover(self, pos: tuple[int, int] | None) -> None:
        self.hovered = bool(pos is not None and self.enabled and self.contains(pos))

    def handle_event(self, event: pygame.event.Event) -> bool:
        """Return True if the event was consumed."""
        return False

    # -- drawing -----------------------------------------------------------

    @abstractmethod
    def draw(self, surface: pygame.Surface, theme: Theme) -> None: ...


class Container(Widget):
    """A widget made of widgets. Hover and events reach the children in order."""

    def __init__(self, children: list[Widget] | None = None) -> None:
        super().__init__()
        self.children: list[Widget] = children or []

    def set_hover(self, pos: tuple[int, int] | None) -> None:
        super().set_hover(pos)
        for child in self.children:
            child.set_hover(pos)

    def handle_event(self, event: pygame.event.Event) -> bool:
        for child in self.children:
            if child.enabled and child.handle_event(event):
                return True
        return False

    def draw(self, surface: pygame.Surface, theme: Theme) -> None:
        for child in self.children:
            child.draw(surface, theme)
