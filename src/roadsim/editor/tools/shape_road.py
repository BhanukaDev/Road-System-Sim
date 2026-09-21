"""Reshaping a placed road by dragging one of its own handles.

Handles are published only for the *selected* road - selecting one changes
nothing about it, so a save file of a road you only looked at is
byte-identical (`road/shape_handle.py`). A click with no handle under it falls
through to `tools/select.py:pick`, so this tool is also how you select a road
in the first place.

**A `CONTROL` or `ARC_MID` handle moves an existing control point; a
`STRAIGHT_MID` one materialises a new one first** (`shape_handle.materialise`)
and then moves that - so a straight-road drag and a curved-road drag are the
same code path once the point exists, exactly the way a lane handle and the
plain centre handle are the same code path once a lever exists
(`editor/tools/move_node.py`). An `ARC_END` handle is different in kind - it
drags `segment.corner_radius`, a scalar shared by every corner on the road,
never a point - so it gets its own drag state and its own command.

The drag itself follows `MoveNodeTool`'s shape exactly: unrecorded steps via a
`Command`'s bare `do()`, then one rewind-and-reapply on release so undo has a
single entry to reverse (D6).

**Alt snaps the curve** (D19). A position drag runs its candidate point
through `curve_snap.snap_curve` first; a radius drag runs the raw radius
through `curve_snap.round_radius`. Both are one call each - the ordering and
the tangent-beats-tidiness precedence live entirely in `curve_snap.py`, so
this file never branches between the snap kinds itself.
"""

from __future__ import annotations

from dataclasses import dataclass

import pygame

from ... import config
from ...geometry import Vec2
from ...road.segment import RoadSegment
from ...road.shape_handle import (
    ShapeHandle,
    ShapeHandleKind,
    materialise,
    radius_for_arc_end,
    shape_handles,
)
from ..commands import SetControlPoints, SetCornerRadius
from ..context import EditorContext, ToolPreview
from ..curve_snap import SnapRequest, round_radius, snap_curve
from ..handle import HandleKind, PreviewHandle
from ..modifiers import Modifiers
from ..tool import Tool
from .select import pick

_HANDLE_KIND = {
    ShapeHandleKind.CONTROL: HandleKind.CONTROL,
    ShapeHandleKind.ARC_MID: HandleKind.ARC_MID,
    ShapeHandleKind.ARC_END: HandleKind.ARC_END,
    ShapeHandleKind.STRAIGHT_MID: HandleKind.STRAIGHT_MID,
}


@dataclass
class _Drag:
    segment_id: int
    index: int | None
    """Control-point index for a position drag; `None` for a radius drag."""
    lever: Vec2
    original_points: tuple[Vec2, ...]
    original_radius: float
    handle: ShapeHandle | None = None
    """The `ARC_END` handle actually grabbed - only set for a radius drag, and
    read only for its `s`, frozen at grab time."""
    reference: RoadSegment | None = None
    """A throwaway, never-registered `RoadSegment` built from the road's shape
    at grab time - only set for a radius drag. `radius_for_arc_end` locates the
    arc by matching `handle.s` against `path.piece_starts`; the live segment's
    own arc boundaries shift as the radius itself changes, so matching against
    it would lose the arc the handle started on. The corner and both tangent
    directions a radius drag actually needs do not depend on the radius at
    all, so a frozen reference answers exactly as well as the live segment
    would - without the live segment's problem."""
    readout: str = ""
    """What the last Alt snap did, if anything - `curve_snap.CurveSnap.readout`
    or `"R {radius} m"`, shown in the HUD so Alt never feels silent."""


class ShapeRoadTool(Tool):
    name = "shape"
    hint = "select a road, then drag a handle   [Alt] snap the curve   [Esc] cancel"

    def __init__(self) -> None:
        self.drag: _Drag | None = None

    def deactivate(self, ctx: EditorContext) -> None:
        self.cancel(ctx)

    def handle_event(self, event: pygame.event.Event, ctx: EditorContext) -> bool:
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            return self.press(ctx, ctx.world(*event.pos))
        if event.type == pygame.MOUSEMOTION:
            ctx.cursor = ctx.world(*event.pos)
            if self.drag is None:
                return False
            if self.drag.segment_id not in ctx.network.segments:
                self.drag = None  # undo can land mid-drag
                return False
            self.drag_to(ctx, ctx.cursor, Modifiers.current().alt)
            return True
        if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            return self.release(ctx)
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            return self.cancel(ctx)
        return False

    # -- picking and grabbing -----------------------------------------------

    def press(self, ctx: EditorContext, point: Vec2) -> bool:
        if self.grab(ctx, point):
            return True
        ctx.select(pick(ctx, point))
        return True

    def grab(self, ctx: EditorContext, point: Vec2) -> bool:
        segment_id = ctx.selection.segment
        if segment_id is None or segment_id not in ctx.network.segments:
            return False
        segment = ctx.network.segments[segment_id]
        handle = _nearest_handle(ctx, segment, point)
        if handle is None:
            return False

        original_points = tuple(segment.control_points)
        original_radius = segment.corner_radius

        if handle.kind is ShapeHandleKind.ARC_END:
            reference = RoadSegment(
                segment.id,
                segment.node_a,
                segment.node_b,
                list(original_points),
                segment.profile,
                corner_radius=original_radius,
            )
            self.drag = _Drag(
                segment_id, None, Vec2(0.0, 0.0), original_points, original_radius,
                handle=handle, reference=reference,
            )
            return True

        points, index = materialise(segment, handle)
        lever = handle.position - points[index]
        self.drag = _Drag(segment_id, index, lever, original_points, original_radius)
        SetControlPoints(segment_id, points).do(ctx.network)  # unrecorded
        return True

    # -- the drag ------------------------------------------------------------

    def drag_to(self, ctx: EditorContext, cursor: Vec2, alt: bool = False) -> None:
        """`alt` is passed in, never read here - `handle_event` is the only
        caller that may touch `Modifiers.current()`, exactly as `MoveNodeTool`
        keeps pygame out of `drag_to` so a test can call this directly with no
        window open."""
        segment = ctx.network.segments[self.drag.segment_id]

        if self.drag.index is None:
            radius = radius_for_arc_end(self.drag.reference, self.drag.handle, cursor)
            self.drag.readout = ""
            if alt:
                radius = round_radius(radius)
                self.drag.readout = f"R {radius:.1f} m"
            SetCornerRadius(self.drag.segment_id, radius).do(ctx.network)  # unrecorded
            return

        points = list(segment.control_points)
        points[self.drag.index] = cursor - self.drag.lever
        self.drag.readout = ""
        if alt:
            req = SnapRequest(
                ctx.network, segment, points, self.drag.index, points[self.drag.index]
            )
            hit = snap_curve(req)
            if hit is not None:
                points[self.drag.index] = hit.position
                self.drag.readout = hit.readout
        SetControlPoints(self.drag.segment_id, points).do(ctx.network)  # unrecorded

    def release(self, ctx: EditorContext) -> bool:
        if self.drag is None:
            return False
        drag, self.drag = self.drag, None
        if drag.segment_id not in ctx.network.segments:
            return True
        segment = ctx.network.segments[drag.segment_id]

        if drag.index is None:
            final = segment.corner_radius
            if final == drag.original_radius:
                return True
            SetCornerRadius(drag.segment_id, drag.original_radius).do(ctx.network)
            ctx.apply(SetCornerRadius(drag.segment_id, final))
            return True

        final_points = list(segment.control_points)
        if tuple(final_points) == drag.original_points:
            return True
        SetControlPoints(drag.segment_id, list(drag.original_points)).do(ctx.network)
        ctx.apply(SetControlPoints(drag.segment_id, final_points))
        return True

    def cancel(self, ctx: EditorContext) -> bool:
        if self.drag is None:
            if not ctx.selection.is_empty:
                ctx.clear_selection()
                return True
            return False
        drag, self.drag = self.drag, None
        if drag.segment_id in ctx.network.segments:
            if drag.index is None:
                SetCornerRadius(drag.segment_id, drag.original_radius).do(ctx.network)
            else:
                SetControlPoints(drag.segment_id, list(drag.original_points)).do(
                    ctx.network
                )
        ctx.status = "reshape cancelled"
        return True

    # -- feedback --------------------------------------------------------

    def preview(self, ctx: EditorContext) -> ToolPreview:
        segment_id = self.drag.segment_id if self.drag else ctx.selection.segment
        if segment_id is None or segment_id not in ctx.network.segments:
            return ToolPreview()
        segment = ctx.network.segments[segment_id]
        handles = [
            PreviewHandle(
                h.position,
                _HANDLE_KIND[h.kind],
                active=self.drag is not None
                and self.drag.index is not None
                and h.kind is ShapeHandleKind.CONTROL
                and h.control_index == self.drag.index,
            )
            for h in shape_handles(segment)
        ]
        return ToolPreview(handles=handles)

    def hud_lines(self, ctx: EditorContext) -> list[str]:
        if self.drag is None:
            return [f"# {self.hint}"]
        if self.drag.index is None:
            segment = ctx.network.segments.get(self.drag.segment_id)
            radius = segment.corner_radius if segment else self.drag.original_radius
            line = f"corner radius {radius:.1f} m (all corners)"
        else:
            line = f"reshaping road {self.drag.segment_id}"
        if self.drag.readout:
            line += f"   snap: {self.drag.readout}"
        return [f"# {self.hint}", line]


def _nearest_handle(
    ctx: EditorContext, segment: RoadSegment, point: Vec2
) -> ShapeHandle | None:
    reach = ctx.snapper.world_radius(config.SHAPE_HANDLE_PX)
    best, best_d = None, reach
    for handle in shape_handles(segment):
        d = handle.position.distance_to(point)
        if d <= best_d:
            best, best_d = handle, d
    return best
