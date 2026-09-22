"""Markings across a lane-count transition - where 2 lanes become 4.

Two arms of different profiles meeting at a node already build a `Junction`
(`_is_through_joint` refuses to call differing profiles a through joint), and
that junction is already drawn as a transition patch. What it had no answer for
was paint: per-segment markings stop dead at each mouth, so the patch between
them came out as bare asphalt with no centre line, no lane lines and nothing
telling a driver a lane was about to appear or disappear.

This derives that paint, the same way everything else at a junction is derived
(D5) - never stored, rebuilt whenever the junction is.

**On lane correspondence.** Pairing lanes here is *geometric, for painting
only*. It carries no user intent, nothing is stored, and it says nothing about
which lane may feed which through a junction - that is lane-to-lane
connectivity, which D5 reserves for M4/M5 precisely because it *does* carry
intent. Nothing in this module should ever be read as that model arriving
early: it answers "where does this line go", not "may I drive here".
"""

from __future__ import annotations

from dataclasses import dataclass

from .. import config
from ..geometry import LineSegment, Path, Vec2, biarc
from .junction import Junction, SegmentEnd, sections_run_through
from .lane import Direction
from .markings import MarkingKind, lane_markings
from .profile import RoadProfile
from .segment import RoadSegment


U_TURN = "arrow_u_turn"
"""The decal painted on every lane of a direction that stops at a transition
- a two-way road becoming one-way (D27). Traffic in it has nowhere to go but
back, and the marking says so where the lane ends."""


@dataclass(frozen=True, slots=True)
class TransitionMarking:
    kind: MarkingKind
    start: Vec2
    end: Vec2
    """The patch's two ends, for anything that only needs endpoints - dedup,
    span-length culling. `curve` is what actually gets drawn."""
    curve: Path
    """`start` to `end`, leaving and arriving along each mouth's own heading.

    A straight chord is only right when both mouths point the same way - two
    arms of a dead-straight width change. Off a bend, the two mouths' frames
    disagree about which way is forward, and a chord between them cuts across
    whatever the road is doing in between, straight through the verge on the
    outside of the curve. A biarc leaves each mouth tangent to its own road, the
    same construction the kerb blend next to it already uses (D17), so a lane
    line bends the way the kerb bends instead of arguing with it. Where the
    mouths really are dead straight, the biarc degenerates to that same chord.
    """
    is_taper: bool = False
    """This line has no partner on the narrow side - it is the edge of a lane
    being gained or lost, running out to where that lane has no width at all."""


@dataclass(frozen=True, slots=True)
class TransitionArrow:
    position: Vec2
    forward: Vec2
    decal: str
    lane_width: float
    """What the arrow has to fit inside. A merge decal is a wide shape, and
    scaling is uniform, so a narrow lane gets a shorter arrow rather than one
    spilling over the line it is telling the driver to cross."""


@dataclass(frozen=True, slots=True)
class LaneTransition:
    node_id: int
    markings: tuple[TransitionMarking, ...]
    arrows: tuple[TransitionArrow, ...]


def build_transition(
    junction: Junction, seg_by_key: dict[tuple[int, bool], RoadSegment]
) -> LaneTransition | None:
    """`None` unless this really is a lane-count transition.

    Three arms or more is a crossing, and a crossing's paint is crosswalks and
    turn arrows rather than lines carried across it. Two arms of the *same*
    profile never reach here at all - `build_junction` calls that a through
    joint and returns nothing.
    """
    if junction.is_degenerate or len(junction.ends) != 2:
        return None
    end_a, end_b = junction.ends
    seg_a = seg_by_key[(end_a.segment_id, end_a.at_a)]
    seg_b = seg_by_key[(end_b.segment_id, end_b.at_a)]
    profile_a = seg_a.profile_at(end_a.at_a)
    profile_b = seg_b.profile_at(end_b.at_a)
    if sections_run_through(seg_a, end_a.at_a, seg_b, end_b.at_a):
        return None

    frame_a = seg_a.end_frame(end_a.at_a)
    frame_b = seg_b.end_frame(end_b.at_a)
    # Each mouth's frame keeps its own segment's A -> B tangent, so two arms
    # drawn in opposite directions have opposing normals and their `+left`
    # offsets mean opposite sides of the same tarmac. One flip here is the
    # whole of it - the alternative is every comparison below carrying a sign.
    flip = -1.0 if frame_a.normal.dot(frame_b.normal) < 0.0 else 1.0
    # Both point the way traffic runs *across the patch* - into the node from
    # `a`'s own road, then straight on out of it along `b`'s (the same pairing
    # `_blends` leaves each junction corner with).
    tangent_a = -frame_a.tangent if end_a.at_a else frame_a.tangent
    tangent_b = frame_b.tangent if end_b.at_a else -frame_b.tangent

    markings = _paired_markings(
        profile_a, profile_b, frame_a, frame_b, flip, tangent_a, tangent_b
    )
    arrows = _arrows(seg_a, end_a, seg_b, end_b)
    if not markings and not arrows:
        return None
    return LaneTransition(junction.node_id, tuple(markings), tuple(arrows))


def build_taper(segment: RoadSegment) -> LaneTransition | None:
    """The paint across a lane-change taper segment (D26).

    The same pairing as a two-arm junction's patch, with the two mouths being
    the taper's own ends: one frame, one direction of travel across it, no
    flip - both profiles are already stored in the taper's A -> B direction.
    """
    if not segment.is_transition or segment.is_broken:
        return None
    frame_a = segment.end_frame(True)
    frame_b = segment.end_frame(False)
    markings = _paired_markings(
        segment.profile,
        segment.profile_b,
        frame_a,
        frame_b,
        1.0,
        frame_a.tangent,
        frame_b.tangent,
    )
    arrows = _taper_arrows(segment)
    if not markings and not arrows:
        return None
    return LaneTransition(segment.node_a, tuple(markings), tuple(arrows))


def carriageway_extents(profile: RoadProfile) -> tuple[float, float]:
    """(left, right) offsets of the vehicle-carrying part of a section - the
    kerbs proper, inside any footway. `(datum, datum)` when nothing drives."""
    lanes = [k for k, lane in enumerate(profile.lanes) if lane.type.carries_vehicles]
    if not lanes:
        return profile.datum, profile.datum
    return profile.edges[min(lanes)], profile.edges[max(lanes) + 1]


def _taper_arrows(segment: RoadSegment) -> list[TransitionArrow]:
    """A merge arrow at the start of each direction that loses a lane across
    the taper - forward traffic reads it at the A end, backward at the B end.

    Set into the taper rather than back up the road before it, because the
    road before it is another segment: the arrow sits where the lane it is
    about to lose still has most of its width.
    """
    start, end = segment.profile, segment.profile_b
    out: list[TransitionArrow] = []
    setback = min(config.TRANSITION_ARROW_SETBACK, segment.carriageway_length / 3.0)
    for towards_b, source, target in ((True, start, end), (False, end, start)):
        leaving = _lane_count(source, towards_b)
        arriving = _lane_count(target, towards_b)
        if leaving == 0 or arriving >= leaving:
            continue
        lanes = _group(source, towards_b)
        s_at = segment.trim_a + setback if towards_b else segment.length - segment.trim_b - setback
        frame = segment.path.sample(segment.path.clamp_s(s_at))
        forward = frame.tangent if towards_b else -frame.tangent
        if arriving == 0:
            # The whole direction stops here: every lane of it turns back.
            for k in lanes:
                out.append(
                    TransitionArrow(
                        frame.position + frame.normal * source.lane_center(k),
                        forward,
                        U_TURN,
                        source.lanes[k].width,
                    )
                )
            continue
        outermost = max(lanes, key=lambda k: abs(source.lane_center(k)))
        centre = source.lane_center(outermost)
        # `centre` is +left in the A -> B frame (D3); in the direction of
        # travel, backward traffic sees that side as its right.
        travel_left = centre if towards_b else -centre
        decal = "arrow_merge_left" if travel_left > 0.0 else "arrow_merge_right"
        out.append(
            TransitionArrow(
                frame.position + frame.normal * centre,
                forward,
                decal,
                source.lanes[outermost].width,
            )
        )
    return out


@dataclass(frozen=True, slots=True)
class _Group:
    """One direction of travel across a profile: its lanes, and its lane
    boundaries ordered from the seam outward to the kerb.

    The *seam* is the side facing the opposite direction - the centre line, or
    the median edge - and it is the edge two roads have to agree on first,
    because that is where traffic is arranged around. Everything else counts
    outward from it, so line `k` of one road's forward group is line `k` of
    the other's whatever the two lane counts are (D27).
    """

    lanes: tuple[int, ...]
    edges: tuple[float, ...]
    """Boundary offsets in the profile's own frame, seam first, kerb last -
    `len(lanes) + 1` of them, marked or not."""
    kinds: tuple[MarkingKind | None, ...]
    """The paint on each of `edges`, `None` where there is none (a kerb
    against a footway)."""
    outward: float
    """+1 when the group extends to the left (+offset) of its seam, -1 when
    to the right - which physical side of the road it lies on."""

    def kind(self, k: int) -> MarkingKind | None:
        return self.kinds[k] if k < len(self.kinds) else None


def _lane_group(profile: RoadProfile, direction: Direction) -> _Group | None:
    """The lanes of `profile` carrying `direction`, as a `_Group`, or `None`.

    A two-way road's group faces its opposite group across the seam. A one-way
    road has no opposite group to face, so handedness says where the seam
    would be (`config.DRIVE_ON_LEFT`): forward traffic keeps left, so a lone
    forward group's seam is on its right, and a lone backward group's on its
    left. That is what lets a one-way road meet a two-way one with its lanes
    continuing the *same-direction* lanes rather than whichever happen to be
    nearest the middle.
    """
    lanes = profile.forward_lanes if direction is Direction.FORWARD else profile.backward_lanes
    if not lanes:
        return None
    other = profile.backward_lanes if direction is Direction.FORWARD else profile.forward_lanes
    lo, hi = min(lanes), max(lanes)
    if other:
        seam_on_left = min(other) < lo  # the other group sits to the left
    else:
        keeps_left = config.DRIVE_ON_LEFT
        seam_on_left = (direction is Direction.BACKWARD) == keeps_left
    edges = profile.edges[lo : hi + 2]  # left (high) to right (low)
    if seam_on_left:
        ordered = tuple(edges)  # seam is the leftmost edge; outward is right
        outward = -1.0
    else:
        ordered = tuple(reversed(edges))
        outward = 1.0
    painted = {round(m.offset, 9): m.kind for m in lane_markings(profile)}
    kinds = tuple(painted.get(round(e, 9)) for e in ordered)
    return _Group(tuple(range(lo, hi + 1)), ordered, kinds, outward)


def _opposite(direction: Direction) -> Direction:
    return Direction.BACKWARD if direction is Direction.FORWARD else Direction.FORWARD


def _kerb_on_side(profile: RoadProfile, left: bool) -> float:
    """The carriageway kerb of `profile` on its own left or right - what a
    line with no partner on that side runs out to, because a road gains or
    loses a lane against its kerb."""
    kerb_left, kerb_right = carriageway_extents(profile)
    return kerb_left if left else kerb_right


def _paired_markings(
    profile_a: RoadProfile,
    profile_b: RoadProfile,
    frame_a,
    frame_b,
    flip: float,
    tangent_a: Vec2,
    tangent_b: Vec2,
) -> list[TransitionMarking]:
    """Every line carried across the patch, one direction of travel at a time.

    `flip` says whether `profile_b` is stored in the same direction as the
    traffic crossing the patch (+1) or the opposite (-1); it decides which of
    B's groups continues A's forward group, and which physical side B's own
    left is. Offsets are used in each profile's own frame throughout - there
    is no shared anchor to shift by, the pairing itself is the alignment.

    Line `k` of a group pairs with line `k` of its counterpart, seam first.
    A line whose partner edge carries no paint is a taper: the lane it bounds
    runs out against the other road's kerb. A whole group with no counterpart
    - a two-way road becoming one-way - runs every line out the same way, and
    `_arrows` puts a U-turn on each of its lanes.
    """

    def at_a(offset: float) -> Vec2:
        return frame_a.position + frame_a.normal * offset

    def at_b(offset: float) -> Vec2:
        return frame_b.position + frame_b.normal * offset

    def line(kind: MarkingKind, start: Vec2, end: Vec2, taper: bool) -> TransitionMarking:
        return TransitionMarking(
            kind, start, end, _marking_curve(start, tangent_a, end, tangent_b), taper
        )

    out: list[TransitionMarking] = []
    for direction in (Direction.FORWARD, Direction.BACKWARD):
        group_a = _lane_group(profile_a, direction)
        group_b = _lane_group(profile_b, direction if flip > 0.0 else _opposite(direction))
        if group_a is None and group_b is None:
            continue
        if group_a is not None and group_b is not None:
            shared = min(len(group_a.edges), len(group_b.edges))
            wider_is_b = len(group_b.lanes) >= len(group_a.lanes)
            for k in range(shared):
                kind_a, kind_b = group_a.kind(k), group_b.kind(k)
                kind = (kind_b if wider_is_b else kind_a) or kind_a or kind_b
                if kind is None:
                    continue
                taper = kind_a is None or kind_b is None
                out.append(line(kind, at_a(group_a.edges[k]), at_b(group_b.edges[k]), taper))
            kerb_b = _kerb_on_side(profile_b, group_a.outward * flip > 0.0)
            for k in range(shared, len(group_a.edges)):
                if group_a.kind(k) is not None:
                    out.append(line(group_a.kind(k), at_a(group_a.edges[k]), at_b(kerb_b), True))
            kerb_a = _kerb_on_side(profile_a, group_b.outward * flip > 0.0)
            for k in range(shared, len(group_b.edges)):
                if group_b.kind(k) is not None:
                    out.append(line(group_b.kind(k), at_a(kerb_a), at_b(group_b.edges[k]), True))
        elif group_a is not None:
            # Stranded: this direction has nowhere to go past the patch.
            kerb_b = _kerb_on_side(profile_b, group_a.outward * flip > 0.0)
            for k, edge in enumerate(group_a.edges):
                if group_a.kind(k) is not None:
                    out.append(line(group_a.kind(k), at_a(edge), at_b(kerb_b), True))
        else:
            # Gained: a direction that starts at the patch.
            kerb_a = _kerb_on_side(profile_a, group_b.outward * flip > 0.0)
            for k, edge in enumerate(group_b.edges):
                if group_b.kind(k) is not None:
                    out.append(line(group_b.kind(k), at_a(kerb_a), at_b(edge), True))
    return _deduped(out)


def _marking_curve(start: Vec2, tangent_a: Vec2, end: Vec2, tangent_b: Vec2) -> Path:
    """`start` to `end`, tangent to each mouth's own heading - a chord when
    that heading agrees, a bend when it does not."""
    return biarc(start, tangent_a, end, tangent_b) or Path.of(LineSegment(start, end))


def _deduped(markings: list[TransitionMarking]) -> list[TransitionMarking]:
    """A centre line belongs to both sides, so it is paired twice - once
    walking out to the left and once to the right. It is one line."""
    seen: set[tuple] = set()
    out: list[TransitionMarking] = []
    for marking in markings:
        key = (
            marking.kind,
            round(marking.start.x, 9),
            round(marking.start.y, 9),
            round(marking.end.x, 9),
            round(marking.end.y, 9),
        )
        if key not in seen:
            seen.add(key)
            out.append(marking)
    return out


def _arrows(
    seg_a: RoadSegment,
    end_a: SegmentEnd,
    seg_b: RoadSegment,
    end_b: SegmentEnd,
) -> list[TransitionArrow]:
    """A merge arrow wherever traffic loses a lane in the direction it travels.

    Only on the losing side. Gaining a lane needs no instruction - a driver
    carries straight on and the new lane simply appears beside them - but
    losing one is a manoeuvre, and it is the one the patch used to say nothing
    about at all.
    """
    out: list[TransitionArrow] = []
    # Each arm in turn as the one traffic arrives *from*. Paired explicitly
    # rather than by identity: a segment can meet itself at a node, and `is`
    # would then pick the wrong end of it.
    for (source, source_end), (target, target_end) in (
        ((seg_a, end_a), (seg_b, end_b)),
        ((seg_b, end_b), (seg_a, end_a)),
    ):
        # Traffic leaving `source` towards the node crosses into `target`.
        profile = source.profile_at(source_end.at_a)
        leaving = _lane_count(profile, not source_end.at_a)
        arriving = _lane_count(target.profile_at(target_end.at_a), target_end.at_a)
        if leaving == 0 or arriving >= leaving:
            continue
        lanes = _group(profile, not source_end.at_a)

        # Set back up its own road, so the arrow is read *before* the taper
        # rather than at the point the lane has already run out. Signed by
        # which end this is, since arc length runs A -> B either way.
        away = 1.0 if source_end.at_a else -1.0
        s_at = source.path.clamp_s(
            source.end_s(source_end.at_a) + away * config.TRANSITION_ARROW_SETBACK
        )
        frame = source.path.sample(s_at)
        forward = -source_end.outgoing_dir
        if arriving == 0:
            # The whole direction stops here: every lane of it turns back.
            for k in lanes:
                out.append(
                    TransitionArrow(
                        frame.position + frame.normal * profile.lane_center(k),
                        forward,
                        U_TURN,
                        profile.lanes[k].width,
                    )
                )
            continue
        outermost = max(lanes, key=lambda k: abs(profile.lane_center(k)))
        centre = profile.lane_center(outermost)
        # `+left` offsets against a normal that points left (D3): a lane left
        # of centre merges right, and the other way round.
        decal = "arrow_merge_left" if centre > 0.0 else "arrow_merge_right"
        out.append(
            TransitionArrow(
                frame.position + frame.normal * centre,
                forward,
                decal,
                profile.lanes[outermost].width,
            )
        )
    return out


def _group(profile: RoadProfile, towards_b: bool) -> tuple[int, ...]:
    return profile.forward_lanes if towards_b else profile.backward_lanes


def _lane_count(profile: RoadProfile, towards_b: bool) -> int:
    return len(_group(profile, towards_b))
