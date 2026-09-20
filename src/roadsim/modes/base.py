"""What a mode is.

A mode is a way of using the same world: looking at it, editing roads in it, and
later running traffic through it. It owns the tools and the interface for that way
of working, and nothing else.

Modes sit above `ui` so they can contribute widgets, and they share **one**
`EditorContext` - the session. A view mode is not a different world from an edit
mode, it is the same world with no mutations: it simply never calls `ctx.apply`.
Giving each mode its own state object would immediately raise the question of
which one owns the network, and there is only one right answer to that.

Adding a mode is a new file plus one line in `modes/__init__.py` (rule 2).
"""

from __future__ import annotations

from abc import ABC, abstractmethod

import pygame

from ..editor.context import EditorContext
from ..render.camera import Camera
from ..ui.widget import Widget


class Mode(ABC):
    name: str = "mode"
    hint: str = ""

    def enter(self, ctx: EditorContext) -> None:
        """Becoming active. Set up anything this mode needs."""

    def leave(self, ctx: EditorContext) -> None:
        """Another mode is taking over. Abandon work in progress, mutate nothing."""

    def handle_event(self, event: pygame.event.Event, ctx: EditorContext) -> bool:
        """Return True if the event was consumed."""
        return False

    def update(self, dt: float, ctx: EditorContext) -> None:
        """Advance by `dt` seconds."""

    def draw(self, surface: pygame.Surface, camera: Camera, ctx: EditorContext) -> None:
        """Draw this mode's own layer. The scene has already drawn the network."""

    def widgets(self, ctx: EditorContext) -> list[Widget]:
        """The bars and panels this mode contributes. Built once on `enter`."""
        return []

    def hud_lines(self, ctx: EditorContext) -> list[str]:
        return [f"# {self.hint}"] if self.hint else []


class ModeBox:
    """The mode registry, in the same shape as `Toolbox` - one active at a time.

    Switching always goes through here, so "leave the old one before entering the
    new one" is guaranteed rather than remembered. A mode abandoning a half-drawn
    road is a `leave`, not a special case at each call site.
    """

    def __init__(self, modes: list[Mode], ctx: EditorContext, active: int = 0) -> None:
        self.modes = modes
        self.ctx = ctx
        self.active_index = active
        self.active.enter(ctx)

    @property
    def active(self) -> Mode:
        return self.modes[self.active_index]

    @property
    def names(self) -> list[str]:
        return [mode.name for mode in self.modes]

    def select(self, index: int) -> Mode:
        if not 0 <= index < len(self.modes) or index == self.active_index:
            return self.active
        self.active.leave(self.ctx)
        self.active_index = index
        self.active.enter(self.ctx)
        self.ctx.status = f"{self.active.name} mode"
        return self.active

    def select_named(self, name: str) -> Mode:
        if name in self.names:
            self.select(self.names.index(name))
        return self.active
