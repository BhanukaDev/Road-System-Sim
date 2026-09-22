"""Applying a cross-section to a road.

The active profile is context state, so `Tab` changes it from anywhere; this
tool is only the brush that paints it onto a segment.
"""

from __future__ import annotations

import pygame

from ...geometry import Vec2
from ..commands import SetProfile
from ..context import EditorContext, Selection, ToolPreview
from ..tool import Tool


class ProfileTool(Tool):
    name = "profile"
    hint = "[Tab] next cross-section   click a road to apply it"

    def handle_event(self, event: pygame.event.Event, ctx: EditorContext) -> bool:
        if event.type == pygame.MOUSEMOTION:
            ctx.cursor = ctx.world(*event.pos)
            return False
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            return self.paint(ctx, ctx.world(*event.pos))
        return False

    def paint(self, ctx: EditorContext, point: Vec2) -> bool:
        snap = ctx.snapper.over_segment(point)
        if snap is None or snap.segment_hit is None:
            return False  # nothing, or the node at a road's end: not a road to paint
        segment_id, _ = snap.segment_hit
        if ctx.network.segments[segment_id].is_transition:
            ctx.status = "a lane change takes its sections from the roads either side"
            return True
        if ctx.network.segments[segment_id].profile is ctx.profile:
            ctx.status = f"already {ctx.profile.name}"
            return True
        ctx.select(Selection(segment=segment_id))
        ctx.apply(SetProfile(segment_id, ctx.profile))
        return True

    def preview(self, ctx: EditorContext) -> ToolPreview:
        return ToolPreview(snap=ctx.snapper.over_segment(ctx.cursor))

    def hud_lines(self, ctx: EditorContext) -> list[str]:
        profile = ctx.profile
        return [
            f"# {self.hint}",
            f"brush: {profile.name}   {profile.total_width:.1f} m"
            f"   {len(profile.lanes)} lanes",
        ]
