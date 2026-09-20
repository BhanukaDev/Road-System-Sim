"""The `Tool` interface.

A tool interprets input and produces `Command`s. It does not mutate the network
(that is `context.apply`) and it does not draw (it returns a `ToolPreview` and
`editor/overlay.py` draws that). Keeping both of those out means a tool can be
driven from a test with no window open.

Adding a tool is a new file plus one line in `toolbox.py` - never a branch in
anything that already exists.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

import pygame

from .context import EditorContext, ToolPreview


class Tool(ABC):
    name: str = "tool"
    hint: str = ""

    def activate(self, ctx: EditorContext) -> None:
        """Called when the tool becomes active. Reset any partial state here."""

    def deactivate(self, ctx: EditorContext) -> None:
        """Called when another tool takes over. Abandon work in progress."""

    @abstractmethod
    def handle_event(self, event: pygame.event.Event, ctx: EditorContext) -> bool:
        """Return True if the event was consumed."""

    def update(self, dt: float, ctx: EditorContext) -> None:
        """Advance by `dt` seconds. Most tools need nothing here."""

    def preview(self, ctx: EditorContext) -> ToolPreview:
        """Work in progress, as geometry. Never a drawing call."""
        return ToolPreview()

    def hud_lines(self, ctx: EditorContext) -> list[str]:
        return [f"# {self.hint}"] if self.hint else []
