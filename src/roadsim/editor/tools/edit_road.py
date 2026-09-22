"""Editing what is already there: move a node, reshape a road, select either.

One tool where there were three (D24). Selecting was a tool of its own, moving
a node another, reshaping a road a third - and in use they are one activity:
you point at a thing and take hold of it. What the press lands on decides what
happens, in the order of how specific the thing is:

1. a shape handle of the *selected* road - drag it (`ShapeRoadTool`);
2. a node - drag it (`MoveNodeTool`), and it becomes the selection;
3. a road - select it, so its shape handles appear;
4. nothing - clear the selection.

The two drags are still their own classes, in their own files, and each can
still be driven alone from a test with no window open: this tool owns one of
each and forwards to whichever the press started. Hover highlighting and
click-to-select are not here at all - `Toolbox` gives them to every tool.
"""

from __future__ import annotations

import pygame

from ...geometry import Vec2
from ..context import EditorContext, ToolPreview
from ..pick import pick
from ..tool import Tool
from .move_node import MoveNodeTool
from .shape_road import ShapeRoadTool


class EditTool(Tool):
    name = "edit"
    hint = (
        "drag a node or a road handle   click a road to select it   "
        "[Shift] 15 deg   [Alt] snap the curve   [Esc] cancel"
    )

    def __init__(self) -> None:
        self.move = MoveNodeTool()
        self.shape = ShapeRoadTool()
        self._active: Tool | None = None
        """Whichever drag the last press started, until it is released."""

    def deactivate(self, ctx: EditorContext) -> None:
        self.cancel(ctx)

    def handle_event(self, event: pygame.event.Event, ctx: EditorContext) -> bool:
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            return self.press(ctx, ctx.world(*event.pos))
        if event.type == pygame.MOUSEMOTION:
            if self._active is None:
                ctx.cursor = ctx.world(*event.pos)
                return False
            return self._active.handle_event(event, ctx)
        if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            return self.release(ctx)
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            return self.cancel(ctx)
        return False

    # -- the press decides -------------------------------------------------

    def press(self, ctx: EditorContext, point: Vec2) -> bool:
        if self.shape.grab(ctx, point):
            self._active = self.shape
            return True
        if self.move.grab(ctx, point):
            self._active = self.move
            return True
        ctx.select(pick(ctx, point))
        return True

    def release(self, ctx: EditorContext) -> bool:
        if self._active is None:
            return False
        active, self._active = self._active, None
        return active.release(ctx)

    def cancel(self, ctx: EditorContext) -> bool:
        if self._active is not None:
            active, self._active = self._active, None
            return active.cancel(ctx)
        if not ctx.selection.is_empty:
            ctx.clear_selection()
            return True
        return False

    @property
    def dragging(self) -> bool:
        return self._active is not None

    # -- feedback --------------------------------------------------------

    def preview(self, ctx: EditorContext) -> ToolPreview:
        """The selected road's shape handles are always on offer; a node drag
        adds its snap and rubber band on top."""
        preview = self.shape.preview(ctx)
        if self._active is self.move:
            moving = self.move.preview(ctx)
            preview.points = moving.points
            preview.rubber_band = moving.rubber_band
            preview.snap = moving.snap
        return preview

    def hud_lines(self, ctx: EditorContext) -> list[str]:
        if self._active is not None:
            return [f"# {self.hint}", *self._active.hud_lines(ctx)[1:]]
        return [f"# {self.hint}"]
