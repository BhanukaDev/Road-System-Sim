"""Where a placed road's own shape can be taken hold of.

Derived from `segment.path.pieces`, never stored - `control_points` stays
authoritative and a save file of a road you only looked at is byte-identical.
Nothing here draws; `editor/tools/shape_road.py` publishes these through a
`ToolPreview` and `editor/overlay.py` is what turns them into pixels (D8).

**Every arc is the fillet of exactly one interior control point.** That is what
`fit_polyline` guarantees (`geometry/fitting.py`), so `ARC_MID` is not a new
degree of freedom - it is a second, better-placed grip on a control point that
already exists, sitting on the arc's own belly rather than at the corner the
fillet cut inside of. Its owner is recovered the way
`editor/tools/draw_road.py:_corner_points` already recovers a fillet's corner
from a fitted path - `ray_ray` between the arc's own entry and exit tangents -
matched to the nearest interior control point. That avoids re-deriving *which*
corners got fillets: `fit_polyline` dedupes its input and skips any corner
`corner_fillet` returned `None` for (collinear, a reversal, or squeezed below
`MIN_RADIUS`), so arc `k` is not corner `k + 1`, and reproducing that decision
here would be a second source of truth for something `fillet.py`'s extraction
exists to keep singular.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum

from ..geometry import ArcSegment, LineSegment, Vec2, deflection, ray_ray
from ..geometry.fillet import MIN_RADIUS
from .network import SNAP_EPS
from .segment import RoadSegment


class ShapeHandleKind(Enum):
    CONTROL = "control"
    """An existing interior control point, at its own (unfilleted) position."""
    ARC_MID = "arc_mid"
    """The belly of a fillet - moves the control point that produced it."""
    ARC_END = "arc_end"
    """Where a fillet leaves or rejoins its straight. Drives `corner_radius`,
    never a position - see `Fillet.tangent_length`, "what a handle measures"."""
    STRAIGHT_MID = "straight_mid"
    """Halfway along a straight. Dragging it inserts a control point there."""


@dataclass(frozen=True, slots=True)
class ShapeHandle:
    segment_id: int
    kind: ShapeHandleKind
    s: float
    """Arc length along `segment.path` - never an abstract `t` (D3)."""
    position: Vec2
    control_index: int | None
    """Set for `CONTROL` and `ARC_MID`, both of which move an existing control
    point. `None` for `STRAIGHT_MID` (dragging it inserts one) and `ARC_END`
    (it moves a radius, not a point)."""


def shape_handles(segment: RoadSegment) -> tuple[ShapeHandle, ...]:
    """Every handle along `segment`, sorted by arc length."""
    path = segment.path
    handles: list[ShapeHandle] = []

    controls = [
        (index, point) for index, point in enumerate(segment.control_points)
    ][1:-1]
    control_s = [(index, point, path.project(point)) for index, point in controls]

    for index, point, s in control_s:
        handles.append(ShapeHandle(segment.id, ShapeHandleKind.CONTROL, s, point, index))

    for piece, s0 in zip(path.pieces, path.piece_starts):
        s1 = s0 + piece.length
        mid_s = s0 + piece.length / 2.0
        if isinstance(piece, LineSegment):
            handles.append(
                ShapeHandle(
                    segment.id,
                    ShapeHandleKind.STRAIGHT_MID,
                    mid_s,
                    path.sample(mid_s).position,
                    None,
                )
            )
        elif isinstance(piece, ArcSegment):
            corner = ray_ray(
                piece.start.position,
                piece.start.tangent,
                piece.end.position,
                piece.end.tangent,
            )
            owner = _owning_control(control_s, corner)
            handles.append(
                ShapeHandle(segment.id, ShapeHandleKind.ARC_END, s0, path.sample(s0).position, None)
            )
            handles.append(
                ShapeHandle(
                    segment.id,
                    ShapeHandleKind.ARC_MID,
                    mid_s,
                    path.sample(mid_s).position,
                    owner,
                )
            )
            handles.append(
                ShapeHandle(segment.id, ShapeHandleKind.ARC_END, s1, path.sample(s1).position, None)
            )

    handles = [h for h in handles if SNAP_EPS < h.s < path.length - SNAP_EPS]
    handles.sort(key=lambda h: h.s)
    return tuple(_dedupe(handles))


def insert_index(segment: RoadSegment, s: float) -> int:
    """Where a new control point at arc length `s` belongs in `control_points`.

    Counts how many existing interior control points already project to an `s`
    below this one - the same idea `road/network.py:_corner_points` uses to
    recover which control points fall inside a span. `Path.project` clamps to
    the nearer endpoint rather than testing containment (D11), so a hairpin can
    order two points wrongly; the failure mode is a strange refit, not a crash,
    and it is the same assumption `split_segment` already makes.
    """
    path = segment.path
    return 1 + sum(
        1 for p in segment.control_points[1:-1] if path.project(p) < s - SNAP_EPS
    )


def materialise(segment: RoadSegment, handle: ShapeHandle) -> tuple[list[Vec2], int]:
    """A control-point list and the index of the point `handle` moves.

    `CONTROL` and `ARC_MID` already own a control point and change nothing.
    `STRAIGHT_MID` inserts one at the handle's own position - collinear with its
    neighbours, so `corner_fillet` reports no corner there and the insertion
    changes nothing about the fitted path until the point is actually dragged.
    `ARC_END` never reaches here; it drives `segment.corner_radius`.
    """
    points = list(segment.control_points)
    if handle.control_index is not None:
        return points, handle.control_index
    if handle.kind is not ShapeHandleKind.STRAIGHT_MID:
        raise ValueError(f"{handle.kind} has no control point to materialise")
    index = insert_index(segment, handle.s)
    points.insert(index, handle.position)
    return points, index


def radius_for_arc_end(
    segment: RoadSegment, handle: ShapeHandle, target: Vec2
) -> float:
    """The corner radius that puts `handle` (an `ARC_END`) at `target`.

    An `ARC_END` sits where a fillet leaves its straight, so it has one degree
    of freedom - how far back from the corner the arc starts, along that
    straight's own tangent, never sideways. `target` is projected onto that
    ray (`Fillet.tangent_length`, "what a handle measures") and the radius is
    read back out of the same identity `corner_fillet` used to build the arc:
    `tangent = radius * tan(phi / 2)`.

    `segment.corner_radius`, unchanged, is the answer whenever `handle.s`
    cannot be matched to an arc - it should always be, since a caller only
    reaches this with a handle `shape_handles` produced.
    """
    path = segment.path
    for piece, s0 in zip(path.pieces, path.piece_starts):
        if not isinstance(piece, ArcSegment):
            continue
        s1 = s0 + piece.length
        at_entry = abs(handle.s - s0) < SNAP_EPS
        at_exit = abs(handle.s - s1) < SNAP_EPS
        if not (at_entry or at_exit):
            continue
        into, out_of = piece.start.tangent, piece.end.tangent
        corner = ray_ray(piece.start.position, into, piece.end.position, out_of)
        if corner is None:
            break
        direction = -into if at_entry else out_of
        traveled = max(0.0, (target - corner).dot(direction))
        half = math.tan(deflection(into, out_of) / 2.0)
        if half < 1e-9:
            break
        return max(MIN_RADIUS, traveled / half)
    return segment.corner_radius


def _owning_control(
    control_s: list[tuple[int, Vec2, float]], corner: Vec2 | None
) -> int | None:
    if corner is None or not control_s:
        return None
    index, _point, _s = min(control_s, key=lambda item: item[1].distance_to(corner))
    return index


def _dedupe(handles: list[ShapeHandle]) -> list[ShapeHandle]:
    """Drop a handle that coincides with the one before it - two arcs abut when
    a straight between them is entirely eaten by both fillets' rooms, leaving
    one `ARC_END` sitting on top of the next."""
    out: list[ShapeHandle] = []
    for handle in handles:
        if out and out[-1].kind is handle.kind and abs(out[-1].s - handle.s) < SNAP_EPS:
            continue
        out.append(handle)
    return out
