"""Junction geometry, derived from the segment ends that meet at a node (D5).

Nothing here is ever stored. A junction is recomputed whenever its node is
dirty, which means a node drag or a profile change cannot leave stale geometry
behind - the failure mode that makes stored junctions a correctness problem.

What it produces is three things:

* a **trim** for each segment end - how far that road must pull back so its
  carriageway stops at the junction mouth rather than ploughing through it;
* a **polygon** for the junction surface, flush with those pulled-back mouths;
* a **corner** rounding the gap between each pair of adjacent mouths, tangent
  to both kerbs and clamped by whichever arm has less straight to give.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from .. import config
from ..geometry import (
    Curve,
    DegenerateOffsetError,
    Fillet,
    Vec2,
    corner_fillet,
    curve_curve,
    deflection,
    ray_ray,
)
from .profile import RoadProfile
from .segment import RoadSegment


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
    corners: tuple[Fillet | None, ...] = ()
    """One entry per CCW-adjacent pair of ends: `corners[i]` rounds the gap
    between `ends[i]` and `ends[(i + 1) % len(ends)]`. `None` where there is no
    corner worth rounding - squeezed below `MIN_RADIUS`, or no room at all."""

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

    seg_by_key = {(seg.id, at_a): seg for seg, at_a in segments}
    demand, corners = _solve_trims(ends, seg_by_key, position)
    lookup = {(seg.id, at_a): demand[(seg.id, at_a)] for seg, at_a in segments}
    polygon = _polygon(ends, segments, lookup)
    return Junction(
        node_id, position, tuple(ends), lookup, polygon, tuple(corners)
    )


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


def _solve_trims(
    ends: list[SegmentEnd],
    seg_by_key: dict[tuple[int, bool], RoadSegment],
    node_position: Vec2,
) -> tuple[dict[tuple[int, bool], float], list[Fillet | None]]:
    """Each end pulls back far enough to clear every neighbour it shares a
    corner with, and never less than its own half-width.

    The corner fillet is solved here too, because the trim *depends on it*: an
    arc tangent to both kerbs touches them at `tangent_length` **beyond** the
    point where those kerbs cross, so an end that stopped at the crossing would
    leave its mouth short of where the corner starts - the junction surface
    bulging past the mouth, and a pavement band floating off the kerb it is
    meant to continue. The trim is therefore `reach + tangent_length`, and the
    corner arc lands exactly on the mouth it was solved with.
    """
    n = len(ends)
    demand = {(e.segment_id, e.at_a): e.half_width for e in ends}
    corners: list[Fillet | None] = [None] * n
    for i, a in enumerate(ends):
        b = ends[(i + 1) % n]
        if a is b:
            continue
        seg_a, seg_b = (
            seg_by_key[(a.segment_id, a.at_a)],
            seg_by_key[(b.segment_id, b.at_a)],
        )
        result = _pair_demand(a, b, seg_a, seg_b, node_position)
        if result is None:
            continue
        fillet, reach_a, reach_b = result
        key_a, key_b = (a.segment_id, a.at_a), (b.segment_id, b.at_a)
        demand[key_a] = max(demand[key_a], reach_a)
        demand[key_b] = max(demand[key_b], reach_b)
        corners[i] = fillet
    return demand, corners


def _pair_demand(
    a: SegmentEnd,
    b: SegmentEnd,
    seg_a: RoadSegment,
    seg_b: RoadSegment,
    node_position: Vec2,
) -> tuple[Fillet | None, float, float] | None:
    """The corner between `a` and `b`, and how far back each end must pull.

    `b` is the next end counter-clockwise, so it sits to `a`'s left: the corner
    between them is bounded by `a`'s left edge and `b`'s right edge.

    The kerbs are each segment's own end piece (`path.pieces[0]` or `[-1]`),
    offset exactly (D1) - not the straight tangent rays M2 used, so a curve
    starting right at the node trims against its real shape instead of the line
    it left on. The tangent-ray version survives only as the fallback for when
    the exact kerbs do not cross nearby: two arms at a shallow angle have kerbs
    that run close to parallel.

    Both ends then pull back past that crossing by the fillet's tangent length,
    so the mouth lands where the corner arc leaves the kerb.
    """
    apex = _exact_apex(seg_a, a, seg_b, b, node_position)
    if apex is None:
        apex = ray_ray(
            node_position + a.outgoing_dir.rot90() * a.extent_left,
            a.outgoing_dir,
            node_position + b.outgoing_dir.rot90() * -b.extent_right,
            b.outgoing_dir,
        )
    if apex is None:
        return None

    limit = config.JUNCTION_MAX_TRIM_FACTOR * max(a.half_width, b.half_width)
    reach_a = min(_reach(seg_a, a.at_a, apex), limit)
    reach_b = min(_reach(seg_b, b.at_a, apex), limit)

    into, out_of = -a.outgoing_dir, b.outgoing_dir
    pull_a, pull_b = seg_a.pull_at(a.at_a), seg_b.pull_at(b.at_a)
    radius = _target_radius(deflection(into, out_of), pull_a, pull_b)
    fillet = corner_fillet(
        apex,
        into,
        out_of,
        radius,
        _room(seg_a, a, reach_a, limit),
        _room(seg_b, b, reach_b, limit),
    )
    tangent = 0.0 if fillet is None else fillet.tangent_length(apex)
    return (
        fillet,
        max(reach_a + tangent, a.half_width),
        max(reach_b + tangent, b.half_width),
    )


def _room(
    segment: RoadSegment, end: SegmentEnd, reach: float, limit: float
) -> float:
    """How much kerb this arm can still give a corner past the kerb crossing.

    Bounded twice: by the end piece the kerb was taken from, so a fillet never
    runs tangent to a straight that has already turned into an arc, and by the
    same max-trim budget that caps `reach` - which is what keeps the total
    trim, `reach + tangent_length`, inside that budget too.
    """
    piece = segment.path.pieces[0] if end.at_a else segment.path.pieces[-1]
    return max(0.0, min(piece.length, limit) - reach)


def _exact_apex(
    seg_a: RoadSegment,
    a: SegmentEnd,
    seg_b: RoadSegment,
    b: SegmentEnd,
    node_position: Vec2,
) -> Vec2 | None:
    """The real crossing of `a`'s left kerb and `b`'s right kerb, or `None` when
    there is none nearby - parallel-enough kerbs, or a kerb offset that would
    collapse the arc it comes from (D1's `DegenerateOffsetError`)."""
    try:
        kerb_a = _kerb_piece(seg_a, a, left=True)
        kerb_b = _kerb_piece(seg_b, b, left=False)
    except DegenerateOffsetError:
        return None
    hits = curve_curve(kerb_a, kerb_b)
    if not hits:
        return None
    return min(hits, key=lambda hit: hit.point.distance_to(node_position)).point


def _kerb_piece(segment: RoadSegment, end: SegmentEnd, *, left: bool) -> Curve:
    """The segment's own end piece, offset out to the kerb `end` names.

    Only the one piece nearest the node - `fit_polyline` guarantees some
    straight run at every end, so the corner this feeds is almost always
    against that straight, and never against a piece the node isn't part of.
    """
    piece = segment.path.pieces[0] if end.at_a else segment.path.pieces[-1]
    return piece.offset(_physical_offset(end, left=left))


def _physical_offset(end: SegmentEnd, *, left: bool) -> float:
    """`end.extent_left`/`extent_right` are already flipped for the view from
    this end (`SegmentEnd.of`); a piece offsets relative to its own fixed A->B
    frame instead, so the flip has to be undone here to get the same physical
    kerb either way."""
    magnitude = end.extent_left if left else end.extent_right
    return magnitude if left == end.at_a else -magnitude


def _reach(segment: RoadSegment, at_a: bool, point: Vec2) -> float:
    """Arc length from the node to `point`'s projection onto the end piece.

    Works for a straight or a curved end piece alike: `Curve.project` measures
    along the piece's own parameterisation, and offsetting never changes that
    parameterisation (a line keeps its direction, an arc keeps its centre and
    angles), so the same call answers this for an exact kerb hit or a ray
    fallback's near-miss.
    """
    piece = segment.path.pieces[0] if at_a else segment.path.pieces[-1]
    s_local = piece.project(point)
    return s_local if at_a else piece.length - s_local


def _target_radius(phi: float, pull_a: float | None, pull_b: float | None) -> float:
    """A corner handle's pull is a tangent length (item 7): the distance back
    from the corner, not a radius. `radius * tan(phi / 2) == tangent_length` is
    `corner_fillet`'s own formula, inverted here so a pull sets both together -
    drag the handle out and the radius grows to match, and the mouth pulls back
    with it, since the trim follows the tangent length."""
    half = math.tan(phi / 2.0)
    candidates = [
        pull / half for pull in (pull_a, pull_b) if pull is not None and half > 1e-9
    ]
    return min(candidates) if candidates else config.JUNCTION_CORNER_RADIUS


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
