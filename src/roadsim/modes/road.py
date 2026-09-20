"""Building roads: the editor, wrapped as a mode.

Everything specific to editing roads lives here - the toolbox, the overlay, the
road bar and the tool row. The scene knows none of it, which is what lets a future
zoning or traffic mode arrive as one file and one registry line rather than as a
set of conditionals in the scene.
"""

from __future__ import annotations

import pygame

from .. import config
from ..editor.context import EditorContext
from ..editor.overlay import EditorOverlay
from ..editor.toolbox import Toolbox
from ..render.camera import Camera
from ..ui.panel import Panel
from ..ui.roadbar import road_bar
from ..ui.toolbar import tool_bar
from ..ui.widget import Widget
from .base import Mode


class RoadMode(Mode):
    name = "roads"
    hint = "pick a road below, then draw   [Tab] next road type   [Del] remove"

    def __init__(self) -> None:
        self.toolbox: Toolbox | None = None
        self.overlay = EditorOverlay()

    # -- lifecycle ---------------------------------------------------------

    def enter(self, ctx: EditorContext) -> None:
        # Built on first entry and kept, so tool state survives a look around in
        # view mode - but see `leave`: work in *progress* does not.
        if self.toolbox is None or self.toolbox.ctx is not ctx:
            self.toolbox = Toolbox(ctx)
        else:
            self.toolbox.active.activate(ctx)

    def leave(self, ctx: EditorContext) -> None:
        """Abandon the half-drawn road. Leaving with points still placed would
        drop them back on screen later, attached to a cursor that has moved."""
        if self.toolbox is not None:
            self.toolbox.active.deactivate(ctx)

    # -- frame -------------------------------------------------------------

    def handle_event(self, event: pygame.event.Event, ctx: EditorContext) -> bool:
        return self.toolbox is not None and self.toolbox.handle_event(event)

    def update(self, dt: float, ctx: EditorContext) -> None:
        if self.toolbox is not None:
            self.toolbox.update(dt)

    def draw(self, surface: pygame.Surface, camera: Camera, ctx: EditorContext) -> None:
        if self.toolbox is None:
            return
        self.overlay.draw(
            surface, camera, ctx.network, ctx.selection, self.toolbox.preview()
        )

    # -- interface ---------------------------------------------------------

    def widgets(self, ctx: EditorContext) -> list[Widget]:
        assert self.toolbox is not None, "widgets() is only asked for once entered"
        tools = tool_bar(self.toolbox, offset=config.UI_BAR_HEIGHT + config.UI_PADDING * 3)
        return [
            road_bar(ctx),
            tools,
            Panel(lambda: self._details(ctx), title="selection", anchor_right=True),
        ]

    def _details(self, ctx: EditorContext) -> list[str]:
        from ..editor.tools.select import describe

        if ctx.selection.is_empty:
            return ["# nothing selected"]
        return [ctx.selection.describe(), *describe(ctx)]

    def hud_lines(self, ctx: EditorContext) -> list[str]:
        if self.toolbox is None:
            return [f"# {self.hint}"]
        return [f"# {self.hint}", *self.toolbox.hud_lines()]
