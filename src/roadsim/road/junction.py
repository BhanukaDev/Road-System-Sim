"""Junction geometry, derived from the segment ends that meet at a node (D5).

Nothing here is ever stored. A junction is recomputed whenever its node is
dirty, which means a node drag or a profile change cannot leave stale geometry
behind - the failure mode that makes stored junctions a correctness problem.

What it produces is two things:

* a **trim** for each segment end - how far that road must pull back so its
  carriageway stops at the junction mouth rather than ploughing through it;
* a **polygon** for the junction surface, flush with those pulled-back mouths.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from .. import config
from ..geometry import Vec2
from .profile import RoadProfile
from .segment import RoadSegment

PARALLEL_EPS = 1e-9


@dataclass(frozen=True, slots=True)
class SegmentEnd:
    """One segment arriving at a node, described from the *node's* point of view.

    `left`/`right` here are relative to `outgoing_dir`, which points away from
    the node. At the `node_b` end the tangent flips - **and so do left and
    right**. Getting that backwards is the classic junction bug, so the flip
    happens exactly once, here.
    """

    segment_id: int
    at_a: bool
    outgoing_dir: Vec2
    extent_left: float
    extent_right: float

    @property
    def angle(self) -> float:
        return self.outgoing_dir.angle

    @property
    def half_width(self) -> float:
        return max(self.extent_left, self.extent_right)

    @staticmethod
    def of(segment: RoadSegment, at_a: bool) -> SegmentEnd:
        profile: RoadProfile = segment.profile
        left, right = profile.extent_left, profile.extent_right
        if not at_a:
            left, right = right, left
        return SegmentEnd(segment.id, at_a, segment.outgoing_dir(at_a), left, right)


@dataclass(frozen=True)
class Junction:
    node_id: int
    position: Vec2
    ends: tuple[SegmentEnd, ...]
    """Sorted counter-clockwise by outgoing direction."""
    trims: dict[tuple[int, bool], float] = field(default_factory=dict)
    """(segment id, at_a) -> metres that end must pull back."""
    polygon: tuple[Vec2, ...] = ()

    @property
    def is_crossing(self) -> bool:
        return len(self.ends) >= 3

    def trim_for(self, segment_id: int, at_a: bool) -> float:
        return self.trims.get((segment_id, at_a), 0.0)


def build_junction(
    node_id: int,
    position: Vec2,
    segments: list[tuple[RoadSegment, bool]],
) -> Junction | None:
    """Derive the junction at a node from the `(segment, at_a)` ends meeting there.

    Returns None when there is nothing to build: a dead end, or two ends of the
    same profile simply running through (a joint in one road, not a junction).
    """
    ends = sorted((SegmentEnd.of(seg, at_a) for seg, at_a in segments), key=_angle_key)
    if len(ends) < 2 or _is_through_joint(ends, segments):
        return None

    trims = _solve_trims(ends)
    lookup = {(seg.id, at_a): trims[(seg.id, at_a)] for seg, at_a in segments}
    polygon = _polygon(ends, segments, lookup)
    return Junction(node_id, position, tuple(ends), lookup, polygon)


def _angle_key(end: SegmentEnd) -> tuple[float, int, bool]:
    # Tie-break on identity so the CCW order is deterministic when two ends
    # leave a node in exactly the same direction.
    return (end.angle % (2.0 * math.pi), end.segment_id, end.at_a)


def _is_through_joint(
    ends: list[SegmentEnd], segments: list[tuple[RoadSegment, bool]]
) -> bool:
    """Two ends of one profile running straight through need no junction.

    Only *straight* through: a sharp kink between two roads still has a corner
    to cut, even when both sides share a cross-section.
    """
    if len(ends) != 2:
        return False
    a, b = segments
    if a[0].profile != b[0].profile:
        return False
    return ends[0].outgoing_dir.dot(ends[1].outgoing_dir) < -0.999


def _solve_trims(ends: list[SegmentEnd]) -> dict[tuple[int, bool], float]:
    """Each end pulls back far enough to clear every neighbour it shares a
    corner with, and never less than its own half-width."""
    demand = {(e.segment_id, e.at_a): e.half_width for e in ends}
    for i, a in enumerate(ends):
        b = ends[(i + 1) % len(ends)]
        if a is b:
            continue
        for end, reach in _pair_demand(a, b):
            key = (end.segment_id, end.at_a)
            demand[key] = max(demand[key], reach)
    return demand


def _pair_demand(a: SegmentEnd, b: SegmentEnd) -> list[tuple[SegmentEnd, float]]:
    """How far `a` and `b` must pull back so their facing kerbs meet at a point.

    `b` is the next end counter-clockwise, so it sits to `a`'s left: the corner
    between them is bounded by `a`'s left edge and `b`'s right edge.

    **M2 approximation:** these are the straight tangent *rays* at the node, not
    the real curves. Fillet clamping guarantees every segment keeps some
    straight run at each end, so roads are near-straight where this matters.
    Exact curve-curve intersection is M3.

    The reach is **capped**. As two arms approach collinear their kerbs approach
    parallel, so the crossing point runs off toward infinity - and a junction
    computed from it swallows the roads feeding it. The cap keeps a shallow
    corner blunt instead, which is wrong by a little rather than by a kilometre.
    M3 fillets the corner properly and the cap goes with the approximation.
    """
    hit = _ray_intersection(
        a.outgoing_dir.rot90() * a.extent_left,
        a.outgoing_dir,
        b.outgoing_dir.rot90() * -b.extent_right,
        b.outgoing_dir,
    )
    if hit is None:
        return []
    limit = config.JUNCTION_MAX_TRIM_FACTOR * max(a.half_width, b.half_width)
    return [
        (a, min(hit.dot(a.outgoing_dir), limit)),
        (b, min(hit.dot(b.outgoing_dir), limit)),
    ]


def _ray_intersection(p: Vec2, u: Vec2, q: Vec2, v: Vec2) -> Vec2 | None:
    """Intersection of `p + t*u` and `q + w*v`, relative to a shared origin."""
    denom = u.cross(v)
    if abs(denom) < PARALLEL_EPS:
        return None  # parallel kerbs: opposite ends of one straight road
    t = (q - p).cross(v) / denom
    return p + u * t


def _polygon(
    ends: list[SegmentEnd],
    segments: list[tuple[RoadSegment, bool]],
    trims: dict[tuple[int, bool], float],
) -> tuple[Vec2, ...]:
    """Walk the ends counter-clockwise, taking each mouth's two corners.

    Corners come from the segment's own frame at its trimmed end rather than
    from the tangent ray, so the junction surface is flush with the ribbons that
    stop against it even where the road is still curving.
    """
    by_key = {(seg.id, at_a): seg for seg, at_a in segments}
    corners: list[Vec2] = []
    for end in ends:
        key = (end.segment_id, end.at_a)
        segment = by_key[key]
        frame = segment.path.sample(_clamped_end_s(segment, end.at_a, trims[key]))
        normal = frame.normal
        left = frame.position + normal * segment.profile.edges[0]
        right = frame.position + normal * segment.profile.edges[-1]
        # Walking CCW we reach the mouth's right corner first, then cross to
        # its left. At a `node_b` end those are the profile's left and right.
        corners.extend((right, left) if end.at_a else (left, right))
    return tuple(corners) if len(corners) >= 3 else ()


def _clamped_end_s(segment: RoadSegment, at_a: bool, trim: float) -> float:
    """Where the mouth sits, kept inside the path even for an over-trimmed road."""
    trim = min(trim, segment.path.length)
    return trim if at_a else segment.path.length - trim
