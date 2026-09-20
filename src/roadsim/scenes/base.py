"""Scene interface.

A scene owns a model and decides what gets drawn. The app owns the window, the
camera and the loop. Adding a new mode (the editor, a traffic sandbox) means a
new Scene subclass registered in `scenes/__init__.py` - never a branch in app.py.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

import pygame

from ..render.camera import Camera


class Scene(ABC):
    name = "scene"

    def __init__(self, camera: Camera) -> None:
        self.camera = camera

    def handle_event(self, event: pygame.event.Event) -> bool:
        """Return True if the event was consumed and the app should ignore it."""
        return False

    def update(self, dt: float) -> None:
        """Advance by `dt` seconds."""

    @abstractmethod
    def draw(self, surface: pygame.Surface) -> None: ...

    def hud_lines(self) -> list[str]:
        return []
