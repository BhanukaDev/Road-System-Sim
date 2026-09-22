"""Picking things, and saying what they are.

Selection is not a tool any more (D24): every tool gets hover and click-to-
select from `Toolbox`, and this module is what it asks. A node wins over the
road it sits on; a road is hit anywhere over its carriageway, not only within
a few pixels of its centreline, because "hover the road" means the asphalt.

The details `describe_selection` puts in the panel are the fastest way to
catch a model bug - a profile whose lanes read wrong, or a trim that has eaten
a road - so it reports derived state, not just ids.
"""

from __future__ import annotations

from ..geometry import Vec2
from .context import EditorContext, Selection
from .highlight import Highlight


def pick(ctx: EditorContext, point: Vec2) -> Selection:
    """What is under a world point."""
    node = ctx.snapper.nearest_node(point)
    if node is not None:
        return Selection(node=node.node_id)
    over = ctx.snapper.over_segment(point)
    if over is None:
        return Selection()
    if over.node_id is not None:
        return Selection(node=over.node_id)  # the last metre of a road is its node
    return Selection(segment=over.segment_hit[0])


def hover_highlights(ctx: EditorContext, point: Vec2) -> list[Highlight]:
    """The thing under `point`, as what the overlay lights. Ids, not geometry,
    for the same reason `ToolPreview.highlights` carries ids (D22)."""
    picked = pick(ctx, point)
    if picked.node is not None:
        return [Highlight.node(picked.node)]
    if picked.segment is not None:
        return [Highlight.segment(picked.segment)]
    return []


def describe(ctx: EditorContext) -> list[str]:
    return describe_selection(ctx, ctx.selection)


def describe_selection(ctx: EditorContext, sel: Selection) -> list[str]:
    """What a node or road is, in words. Takes the selection rather than
    reading it, so a mode can report what the cursor is *over* as well."""
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
    section = f"  {profile.name}   {profile.total_width:.1f} m wide   {way}"
    if seg.is_transition:
        section = (
            f"  lane change: {profile.name} ({profile.total_width:.1f} m) ->"
            f" {seg.profile_b.name} ({seg.profile_b.total_width:.1f} m)"
        )
    lines = [
        section,
        f"  length {seg.length:.1f} m   trims {seg.trim_a:.1f} / {seg.trim_b:.1f}"
        f"   carriageway {seg.carriageway_length:.1f} m",
        f"  {lanes}",
    ]
    if seg.is_too_short:
        lines.append("  TOO SHORT - its junctions have eaten it")
    if seg.is_degenerate:
        lines.append(
            f"  TOO TIGHT - a curve leaves {seg.tightest_clearance():.1f} m at the"
            f" inner edge of a {profile.total_width:.1f} m road"
        )
    return lines

