"""Snapping a dragged shape-handle point to tidy values while Alt is held.

Pure functions of geometry - no pygame, no mutation - testable with no window,
the same reasoning `road/` is held to. Lives in `editor/`, not `geometry/`:
it needs `config.ANGLE_SNAP_DEG` and a radius ladder, and `geometry/` never
imports `config` (D3's layering runs one way).

Two position snaps and one radius snap, in a fixed order that is a decision
rather than an accident - see D19 in `docs/decisions.md`. **Tangent continuity
beats heading quantisation**: a kink where two roads meet is a fact about the
*network*, which nothing else here can cause or cure, while a 15-degree corner
is a tidiness preference about one road alone. The radius snap never competes
with either - it acts on a scalar an `ARC_END` handle drags, never a point.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable

from .. import config
from ..geometry import Vec2, deflection, ray_ray
from ..geometry.fillet import MIN_RADIUS
from ..road.network import RoadNetwork
from ..road.segment import RoadSegment


@dataclass(frozen=True, slots=True)
class SnapRequest:
    network: RoadNetwork
    segment: RoadSegment
    points: list[Vec2]
    """Candidate control-point list - the dragged point is already at `target`,
    living at `points[index]`, so a snap function can read its neighbours."""
    index: int
    target: Vec2


@dataclass(frozen=True, slots=True)
class CurveSnap:
    position: Vec2
    readout: str
    """What snapped - `"tangent"` or `"37 deg"` - shown in the HUD so holding
    Alt never feels like the editor silently fighting the cursor."""


def tangent_continuity(req: SnapRequest) -> CurveSnap | None:
    """Only for a point adjacent to a node end. `fit_polyline` already keeps a
    road tangent-continuous with *itself* - the only real kink is where it
    meets another road at a shared node, so this looks nowhere else.

    Picks whichever other arm at that node is closest to the drag's own
    direction, then projects the target onto the ray that continues straight
    through the node from that arm - the same "distance travelled along a
    direction" idiom `Snapper.nearest_anchor` already uses.
    """
    end = _node_end(req)
    if end is None:
        return None
    node_id, anchor = end
    arms = [
        seg.outgoing_dir(at_a)
        for seg, at_a in req.network.segments_at(node_id)
        if seg.id != req.segment.id
    ]
    if not arms:
        return None
    leg = req.target - anchor
    if leg.length_sq < 1e-12:
        return None
    leg_dir = leg.normalized()
    arm = max(arms, key=lambda d: abs(d.normalized().dot(leg_dir)))
    line = -arm  # continue straight through the node, not back along the arm
    traveled = max(0.0, leg.dot(line))
    return CurveSnap(anchor + line * traveled, "tangent")


def heading_quantise(req: SnapRequest) -> CurveSnap | None:
    """Quantise both legs' *absolute* headings to `ANGLE_SNAP_DEG`, matching
    `Snapper._constrain` so Shift and Alt agree what a round angle is, and
    intersect them - a fillet's sweep is the deflection between its two legs
    (`geometry.deflection`), so quantising both legs quantises the turn.
    """
    if req.index <= 0 or req.index >= len(req.points) - 1:
        return None
    prev, nxt = req.points[req.index - 1], req.points[req.index + 1]
    into_raw, out_raw = req.target - prev, nxt - req.target
    if into_raw.length_sq < 1e-12 or out_raw.length_sq < 1e-12:
        return None

    step = math.radians(config.ANGLE_SNAP_DEG)
    u = Vec2.from_angle(round(into_raw.angle / step) * step)
    v = Vec2.from_angle(round(out_raw.angle / step) * step)
    hit = ray_ray(prev, u, nxt, -v)
    if hit is None:
        return None  # parallel legs - no corner to snap to
    if (hit - prev).dot(u) <= 0.0 or (nxt - hit).dot(v) <= 0.0:
        return None  # the solution lies behind one of the rays
    return CurveSnap(hit, f"{math.degrees(deflection(u, v)):.0f} deg")


def round_radius(raw: float) -> float:
    """The nearest rung of `config.RADIUS_LADDER`, floored at `MIN_RADIUS`."""
    if raw <= config.RADIUS_LADDER[0]:
        return max(MIN_RADIUS, config.RADIUS_LADDER[0])
    return min(config.RADIUS_LADDER, key=lambda rung: abs(rung - raw))


CurveSnapFn = Callable[[SnapRequest], "CurveSnap | None"]

CURVE_SNAPS: tuple[CurveSnapFn, ...] = (tangent_continuity, heading_quantise)
"""First entry that bites, wins (D19). A new position snap is a new function
plus one line here - never a branch inside an existing one."""


def snap_curve(req: SnapRequest) -> CurveSnap | None:
    for fn in CURVE_SNAPS:
        hit = fn(req)
        if hit is not None:
            return hit
    return None


def _node_end(req: SnapRequest) -> tuple[int, Vec2] | None:
    """Which node, if any, `req.index` sits next to.

    A road with exactly one interior point between two junctions has that
    point adjacent to *both* ends at once; this answers node_a first; the
    ambiguity is the same one `RoadSegment.is_at_a` documents for a loop.
    """
    if req.index == 1:
        node_id = req.segment.node_a
    elif req.index == len(req.points) - 2:
        node_id = req.segment.node_b
    else:
        return None
    return node_id, req.network.nodes[node_id].position
