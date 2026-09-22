"""Junction geometry, derived from the segment ends that meet at a node (D5).

Nothing here is ever stored. A junction is recomputed whenever its node is
dirty, which means a node drag or a profile change cannot leave stale geometry
behind - the failure mode that makes stored junctions a correctness problem.

What it produces is four things:

* a **trim** for each segment end - how far that road must pull back so its
  carriageway stops at the junction mouth rather than ploughing through it;
* a **polygon** for the junction surface, flush with those pulled-back mouths;
* a **corner** rounding the gap between each pair of adjacent mouths, tangent
  to both kerbs and clamped by whichever arm has less straight to give - which
  is what sets the trim, since a mouth has to reach the corner it starts at;
* a **blend** between each adjacent pair of mouths: the kerb actually drawn,
  a biarc that meets both mouths in position and heading (D17). The corner
  decides *where* the mouths go; the blend joins the mouths that resulted.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from .. import config
from ..geometry import (
    Curve,
    DegenerateOffsetError,
    Fillet,
    Path,
    Vec2,
    biarc,
    corner_fillet,
    deflection,
    is_simple,
    path_intersections,
    ray_ray,
)
from .profile import RoadProfile
from .segment import RoadSegment

_REACH_EPS = 1e-9
"""A projection this close to the far end of a road counts as having run off
it - see `_reach`."""

_GORE_PHI = math.pi - math.radians(config.GORE_ANGLE_DEG)
"""Deflection above which a corner is a gore nose. `phi` is measured between
the direction arriving and the direction leaving, so two arms `eps` apart make
a corner of `pi - eps`: shallow arms are a *large* deflection."""


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
        profile: RoadProfile = segment.profile_at(at_a)
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
    corner worth rounding - squeezed below `MIN_RADIUS`, or no room at all.

    This is the *trim solver's* corner: it is solved at the kerbs' apex, and its
    tangent length is what tells each mouth how far to pull back. It is not the
    kerb that gets drawn - see `blends`."""
    blends: tuple[Path | None, ...] = ()
    """The kerb actually run between each CCW-adjacent pair of mouths.

    Same indexing as `corners`: `blends[i]` leaves `ends[i]`'s left mouth corner
    along that road's own tangent and arrives at `ends[i + 1]`'s right corner
    along that road's. A biarc, so it matches both mouths exactly in position
    *and* direction - which a chord does not (the triangular gore) and neither
    does `corners[i]` once anything moves a mouth off the apex it was solved at:
    a half-width floor, a budget clamp, or simply an arm whose own curvature
    turns the mouth frame away from the tangent ray. Being arcs, it offsets
    exactly, so `road/pavement.py` gets a footway that follows it for free."""
    is_degenerate: bool = False
    """This node has no honest junction geometry, and nothing should be filled
    from it.

    Two ways to earn it, both of which used to be drawn anyway: a pair of arms
    whose kerbs do not separate within the budget either road can give (a
    shallow merge on roads too short to hold the gore it needs), and a mouth
    ring that crosses itself. The first drew two carriageways through each
    other, the second filled as bowties and holes. Flagged rather than raised,
    and drawn loudly - the same discipline as `RoadSegment.is_degenerate`."""

    @property
    def is_crossing(self) -> bool:
        return len(self.ends) >= 3

    def trim_for(self, segment_id: int, at_a: bool) -> float:
        return self.trims.get((segment_id, at_a), 0.0)


def build_junction(
    node_id: int,
    position: Vec2,
    segments: list[tuple[RoadSegment, bool]],
    run_lengths: dict[tuple[int, bool], float] | None = None,
) -> Junction | None:
    """Derive the junction at a node from the `(segment, at_a)` ends meeting there.

    Returns None when there is nothing to build: a dead end, or two ends of the
    same profile simply running through (a joint in one road, not a junction).

    `run_lengths` is how much road each arm has behind it, joints included
    (`RoadNetwork.run_length`); it sizes the trim budget. Left out, each arm
    is taken to be its own whole road.
    """
    ends = sorted((SegmentEnd.of(seg, at_a) for seg, at_a in segments), key=_angle_key)
    if len(ends) < 2 or _is_through_joint(ends, segments):
        return None

    seg_by_key = {(seg.id, at_a): seg for seg, at_a in segments}
    runs = {
        key: (run_lengths or {}).get(key, seg.path.length)
        for key, seg in seg_by_key.items()
    }
    demand, corners, unresolved = _solve_trims(ends, seg_by_key, position, runs)
    lookup = {(seg.id, at_a): demand[(seg.id, at_a)] for seg, at_a in segments}
    mouths = _mouths(ends, segments, lookup)
    polygon = tuple(point for mouth in mouths for point in mouth[:2])
    degenerate = unresolved or not is_simple(polygon)
    return Junction(
        node_id,
        position,
        tuple(ends),
        lookup,
        polygon if len(polygon) >= 3 else (),
        tuple(corners),
        _blends(mouths),
        degenerate,
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
    (seg_a, a_at_a), (seg_b, b_at_a) = segments
    if not sections_run_through(seg_a, a_at_a, seg_b, b_at_a):
        return False
    return ends[0].outgoing_dir.dot(ends[1].outgoing_dir) < -0.999


def section_leaving(segment: RoadSegment, at_a: bool) -> RoadProfile:
    """The cross-section of `segment` at its `at_a` end, as seen travelling
    *away* from the node there: left-to-right in the direction of departure.
    Leaving along A -> B is the profile as stored; leaving along B -> A is its
    mirror."""
    profile = segment.profile_at(at_a)
    return profile if at_a else profile.mirrored()


def sections_run_through(
    seg_a: RoadSegment, a_at_a: bool, seg_b: RoadSegment, b_at_a: bool
) -> bool:
    """Two ends at one node carry the same tarmac straight through.

    Compared *physically* - each section oriented as it leaves the node, one
    of them mirrored so both read in one direction of travel - rather than by
    profile identity. Identity was wrong two ways round: two symmetric roads
    joined head to head are one road but had different orientations, and an
    asymmetric road joined head to head to itself has its wide side switching
    kerbs at the joint, which is a lane change and not a through joint at all.
    A taper's end reads its own end's profile (`RoadSegment.profile_at`), so a
    taper continues the road it was drawn from without a seam (D26).
    """
    leaving_a = section_leaving(seg_a, a_at_a)
    leaving_b = section_leaving(seg_b, b_at_a)
    return leaving_a.same_section(leaving_b.mirrored())


def _solve_trims(
    ends: list[SegmentEnd],
    seg_by_key: dict[tuple[int, bool], RoadSegment],
    node_position: Vec2,
    runs: dict[tuple[int, bool], float],
) -> tuple[dict[tuple[int, bool], float], list[Fillet | None], bool]:
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
    unresolved = False
    for i, a in enumerate(ends):
        b = ends[(i + 1) % n]
        if a is b:
            continue
        seg_a, seg_b = (
            seg_by_key[(a.segment_id, a.at_a)],
            seg_by_key[(b.segment_id, b.at_a)],
        )
        key_a, key_b = (a.segment_id, a.at_a), (b.segment_id, b.at_a)
        result = _pair_demand(
            a, b, seg_a, seg_b, node_position, runs[key_a], runs[key_b]
        )
        if result is None:
            continue
        fillet, reach_a, reach_b, pair_unresolved = result
        demand[key_a] = max(demand[key_a], reach_a)
        demand[key_b] = max(demand[key_b], reach_b)
        corners[i] = fillet
        unresolved = unresolved or pair_unresolved
    return demand, corners, unresolved


def _pair_demand(
    a: SegmentEnd,
    b: SegmentEnd,
    seg_a: RoadSegment,
    seg_b: RoadSegment,
    node_position: Vec2,
    run_a: float,
    run_b: float,
) -> tuple[Fillet | None, float, float, bool] | None:
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

    floor = config.JUNCTION_MAX_TRIM_FACTOR * max(a.half_width, b.half_width)
    limit_a = _trim_budget(seg_a, floor, run_a)
    limit_b = _trim_budget(seg_b, floor, run_b)
    raw_a, raw_b = _reach(seg_a, a.at_a, apex), _reach(seg_b, b.at_a, apex)

    # Unresolved means the kerbs do not separate inside what either road can
    # give. The old code clamped to the cap and carried on, which is precisely
    # how two shallow arms ended up drawn through each other.
    unresolved = (
        raw_a is None or raw_b is None or raw_a > limit_a or raw_b > limit_b
    )
    reach_a = min(limit_a if raw_a is None else raw_a, limit_a)
    reach_b = min(limit_b if raw_b is None else raw_b, limit_b)

    into, out_of = -a.outgoing_dir, b.outgoing_dir
    pull_a, pull_b = seg_a.pull_at(a.at_a), seg_b.pull_at(b.at_a)
    radius = _target_radius(deflection(into, out_of), pull_a, pull_b)
    fillet = corner_fillet(
        apex,
        into,
        out_of,
        radius,
        _room(seg_a, a, reach_a, limit_a),
        _room(seg_b, b, reach_b, limit_b),
    )
    tangent = 0.0 if fillet is None else fillet.tangent_length(apex)
    return (
        fillet,
        max(reach_a + tangent, a.half_width),
        max(reach_b + tangent, b.half_width),
        unresolved,
    )


def _trim_budget(segment: RoadSegment, floor: float, run_length: float) -> float:
    """How far this arm may be pulled back before the junction is giving up.

    A width multiple alone has no angle term, and a shallow merge's demand is
    all angle - so the budget also grows with the arm's own length, which is
    what lets a long ramp hold the long gore it genuinely needs while a stub
    still cannot be eaten by its own junction (`config.JUNCTION_MAX_TRIM_FACTOR`).

    The length is the *run* - this segment plus whatever continues straight
    through same-profile joints beyond it (`RoadNetwork.run_length`) - because
    a road cut into pieces (D24) is not a row of stubs. The trim itself still
    has to fit inside this segment: it can never reach past the far node, so
    the budget is capped at the segment less the carriageway it must keep.
    """
    budget = max(floor, config.JUNCTION_MAX_TRIM_FRACTION * run_length)
    return min(budget, max(floor, segment.path.length - config.MIN_CARRIAGEWAY))


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
    there is none at all - kerbs parallel the whole way, or a kerb offset that
    would collapse the arc it comes from (D1's `DegenerateOffsetError`).

    Searched along the whole kerb rather than just the end piece. Two arms at a
    shallow angle cross tens of metres out, which is off the end of any one
    piece: looking only at the first piece reports "no crossing", falls through
    to the tangent-ray fallback, and the result was then capped back to a trim
    that left the two carriageways overlapping.
    """
    kerb_a = _kerb_run(seg_a, a, left=True)
    kerb_b = _kerb_run(seg_b, b, left=False)
    if kerb_a is None or kerb_b is None:
        return None
    hits = path_intersections(kerb_a, kerb_b)
    if not hits:
        return None
    return min(hits, key=lambda hit: hit.point.distance_to(node_position)).point


def _kerb_run(segment: RoadSegment, end: SegmentEnd, *, left: bool) -> Path | None:
    """The kerb `end` names, from the node outward for as far as it offsets.

    Walking outward from the node and stopping at the first piece that cannot
    take the offset keeps the run contiguous with the mouth: a tight curve
    further along the road ends the search rather than punching a hole in the
    middle of it. `None` when even the first piece collapses.

    Pieces are collected outward but returned in the path's own A -> B order,
    because that is the only order in which they chain into a valid `Path`.
    """
    d = _physical_offset(end, left=left)
    if segment.is_transition:
        # A taper's kerb is the line between its two mouths' edges (D28), not
        # an offset of its chord - and it is one straight, so it is the run.
        return Path.of(segment.kerb_line(left=d >= 0.0))
    pieces = segment.path.pieces
    outward = pieces if end.at_a else tuple(reversed(pieces))
    run: list[Curve] = []
    for piece in outward:
        try:
            run.append(piece.offset(d))
        except DegenerateOffsetError:
            break
    if not run:
        return None
    if not end.at_a:
        run.reverse()
    return Path(tuple(run))


def _physical_offset(end: SegmentEnd, *, left: bool) -> float:
    """`end.extent_left`/`extent_right` are already flipped for the view from
    this end (`SegmentEnd.of`); a piece offsets relative to its own fixed A->B
    frame instead, so the flip has to be undone here to get the same physical
    kerb either way."""
    magnitude = end.extent_left if left else end.extent_right
    return magnitude if left == end.at_a else -magnitude


def _reach(segment: RoadSegment, at_a: bool, point: Vec2) -> float | None:
    """Arc length from the node to `point`'s foot on this arm's centreline, or
    `None` when that foot runs off the far end of the road.

    Measured on the centreline rather than on the kerb because the trim *is* a
    centreline arc length - it is the station `_polygon` samples to build the
    mouth. For a straight end the two agree exactly; on an arc they do not,
    because offsetting changes a curve's radius and therefore its length.

    The `None` matters as much as the number. `Path.project` clamps (D11's
    warning about `project` not being a containment test), so an apex beyond
    the end of the road comes back *at* the end looking like a reachable
    answer. Taken at face value that is the shallow-Y overlap: a mouth placed
    where the kerbs have not separated yet.
    """
    path = segment.path
    s = path.project(point)
    reach = s if at_a else path.length - s
    if reach >= path.length - _REACH_EPS:
        return None
    return max(reach, 0.0)


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
    if candidates:
        return min(candidates)
    # A near-straight-through corner is a merge, not a turn, and wants a gore
    # nose's tight kerb. Asking for `JUNCTION_CORNER_RADIUS` there needs a
    # tangent of `radius * tan(phi / 2)` - ~69 m at 6 m and 170 degrees - which
    # the room available clamps until the fitted radius collapses below
    # `MIN_RADIUS` and `corner_fillet` gives up entirely.
    if phi > _GORE_PHI:
        return config.GORE_NOSE_RADIUS
    return config.JUNCTION_CORNER_RADIUS


def _mouths(
    ends: list[SegmentEnd],
    segments: list[tuple[RoadSegment, bool]],
    trims: dict[tuple[int, bool], float],
) -> list[tuple[Vec2, Vec2, Vec2]]:
    """Each end's mouth, walking the ends counter-clockwise.

    One `(first corner, second corner, direction into the node)` per end, where
    the corners are in CCW order around the junction: walking CCW we reach the
    mouth's right corner first, then cross to its left, and at a `node_b` end
    those are the profile's left and right.

    Corners and direction both come from the segment's own frame at its trimmed
    end rather than from the tangent ray at the node, so the junction surface is
    flush with the ribbons that stop against it - and the blend leaving the mouth
    leaves along the road's real heading - even where the road is still curving.
    """
    by_key = {(seg.id, at_a): seg for seg, at_a in segments}
    mouths: list[tuple[Vec2, Vec2, Vec2]] = []
    for end in ends:
        key = (end.segment_id, end.at_a)
        segment = by_key[key]
        frame = segment.frame_at(_clamped_end_s(segment, end.at_a, trims[key]), end.at_a)
        normal = frame.normal
        profile = segment.profile_at(end.at_a)
        left = frame.position + normal * profile.edges[0]
        right = frame.position + normal * profile.edges[-1]
        # The path's tangent runs A -> B regardless of which end this is, so at
        # the `node_a` end it already points away from the node and has to be
        # flipped to describe traffic arriving.
        into = -frame.tangent if end.at_a else frame.tangent
        first, second = (right, left) if end.at_a else (left, right)
        mouths.append((first, second, into))
    return mouths


def _blends(mouths: list[tuple[Vec2, Vec2, Vec2]]) -> tuple[Path | None, ...]:
    """The kerb between each CCW-adjacent pair of mouths, as a biarc.

    From one mouth's second corner to the next mouth's first - the two points
    either side of the gap the old code cut straight across. Each end keeps its
    own road's heading, so the kerb leaves one carriageway and joins the other
    without a kink, and how much it bows is set by how far apart the two mouths
    are and how much they disagree about direction. That is the whole of "add
    curvature based on the orientation": a gore between two nearly parallel arms
    gets the long shallow nose it should have, and a right-angle corner gets a
    quarter-turn, from the same construction.
    """
    n = len(mouths)
    if n < 2:
        return ()
    blends: list[Path | None] = []
    for i in range(n):
        _, leaving, into_a = mouths[i]
        arriving, _, into_b = mouths[(i + 1) % n]
        blends.append(biarc(leaving, into_a, arriving, -into_b))
    return tuple(blends)


def _clamped_end_s(segment: RoadSegment, at_a: bool, trim: float) -> float:
    """Where the mouth sits, kept inside the path even for an over-trimmed road."""
    trim = min(trim, segment.path.length)
    return trim if at_a else segment.path.length - trim
