"""Picking things, and saying what they are.

The details this puts in the HUD are the fastest way to catch a model bug - a
profile whose lanes read wrong, or a trim that has eaten a road - so it reports
derived state, not just ids.
"""

from __future__ import annotations

import pygame

from ...geometry import Vec2
from ..context import EditorContext, Selection, ToolPreview
from ..snapping import SnapKind
from ..tool import Tool


class SelectTool(Tool):
    name = "select"
    hint = "click a node or a road   [Delete] remove it   [Esc] deselect"

    def handle_event(self, event: pygame.event.Event, ctx: EditorContext) -> bool:
        if event.type == pygame.MOUSEMOTION:
            ctx.cursor = ctx.world(*event.pos)
            return False
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            ctx.select(pick(ctx, ctx.world(*event.pos)))
            return True
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            if not ctx.selection.is_empty:
                ctx.clear_selection()
                return True
        return False

    def preview(self, ctx: EditorContext) -> ToolPreview:
        return ToolPreview(snap=ctx.snapper.snap(ctx.cursor))

    def hud_lines(self, ctx: EditorContext) -> list[str]:
        return [f"# {self.hint}", f"selected: {ctx.selection.describe()}", *describe(ctx)]


def pick(ctx: EditorContext, point: Vec2) -> Selection:
    """What is under a world point. A node wins over the road it sits on."""
    snap = ctx.snapper.snap(point)
    if snap.kind is SnapKind.NODE:
        return Selection(node=snap.node_id)
    if snap.kind is SnapKind.SEGMENT:
        return Selection(segment=snap.segment_hit[0])
    return Selection()


def describe(ctx: EditorContext) -> list[str]:
    sel = ctx.selection
    if sel.node is not None and sel.node in ctx.network.nodes:
        return _describe_node(ctx, sel.node)
    if sel.segment is not None and sel.segment in ctx.network.segments:
        return _describe_segment(ctx, sel.segment)
    return []


def _describe_node(ctx: EditorContext, node_id: int) -> list[str]:
    node = ctx.network.nodes[node_id]
    junction = ctx.network.junctions.get(node_id)
    where = f"({node.position.x:.1f}, {node.position.y:.1f})"
    kind = f"junction of {len(junction.ends)}" if junction else "no junction"
    return [f"  at {where}   degree {node.degree}   {kind}"]


def _describe_segment(ctx: EditorContext, segment_id: int) -> list[str]:
    seg = ctx.network.segments[segment_id]
    profile = seg.profile
    lanes = " ".join(
        f"{lane.type.value[:4]}/{lane.direction.value[:3]}" for lane in profile.lanes
    )
    way = "one-way" if profile.is_oneway else "two-way"
    lines = [
        f"  {profile.name}   {profile.total_width:.1f} m wide   {way}",
        f"  length {seg.length:.1f} m   trims {seg.trim_a:.1f} / {seg.trim_b:.1f}"
        f"   carriageway {seg.carriageway_length:.1f} m",
        f"  {lanes}",
    ]
    if seg.is_too_short:
        lines.append("  TOO SHORT - its junctions have eaten it")
    return lines
