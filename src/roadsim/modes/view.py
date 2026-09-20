"""Looking at the network without touching it.

The mode that proves the split is real: it has the whole context and never calls
`ctx.apply`, so nothing it does can change the world. Everything it shows is read
off the model, which also makes it the fastest way to inspect a suspect junction
without risking a stray click turning into a road.
"""

from __future__ import annotations

import pygame

from ..editor.context import EditorContext, Selection
from ..editor.tools.select import describe_selection, pick
from ..render.camera import Camera
from ..render.curves import to_screen_points
from ..ui.panel import Panel
from ..ui.widget import Widget
from .. import config
from .base import Mode


class ViewMode(Mode):
    name = "view"
    hint = "look around   click to inspect a road or node   nothing here edits"

    def __init__(self) -> None:
        self.hover: Selection = Selection()

    def enter(self, ctx: EditorContext) -> None:
        self.hover = Selection()

    def handle_event(self, event: pygame.event.Event, ctx: EditorContext) -> bool:
        if event.type == pygame.MOUSEMOTION:
            ctx.cursor = ctx.world(*event.pos)
            self.hover = pick(ctx, ctx.cursor)
            return False  # the camera still wants to see this
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            ctx.select(pick(ctx, ctx.world(*event.pos)))
            return True
        return False

    def draw(self, surface: pygame.Surface, camera: Camera, ctx: EditorContext) -> None:
        """Outline what the cursor is over. No handles, no snap marks - this mode
        is not offering to do anything, so it must not look like it is."""
        segment_id = self.hover.segment
        if segment_id is None or segment_id not in ctx.network.segments:
            return
        segment = ctx.network.segments[segment_id]
        points = to_screen_points(camera, segment.path.points(camera.world_tolerance))
        if len(points) >= 2:
            pygame.draw.lines(surface, config.Color.UI_ACCENT, False, points, 2)

    def widgets(self, ctx: EditorContext) -> list[Widget]:
        return [Panel(lambda: self._details(ctx), title="under the cursor", anchor_right=True)]

    def _details(self, ctx: EditorContext) -> list[str]:
        if self.hover.is_empty:
            return ["# nothing under the cursor"]
        return [self.hover.describe(), *describe_selection(ctx, self.hover)]

    def hud_lines(self, ctx: EditorContext) -> list[str]:
        return [f"# {self.hint}"]
