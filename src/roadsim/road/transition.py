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
from .junction import Junction, SegmentEnd
from .markings import LaneMarking, MarkingKind, lane_markings
from .profile import RoadProfile
from .segment import RoadSegment


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
    if seg_a.profile == seg_b.profile:
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
        seg_a.profile, seg_b.profile, frame_a, frame_b, flip, tangent_a, tangent_b
    )
    arrows = _arrows(seg_a, end_a, seg_b, end_b)
    if not markings and not arrows:
        return None
    return LaneTransition(junction.node_id, tuple(markings), tuple(arrows))


def _anchor(profile: RoadProfile) -> float:
    """The offset the two cross-sections are lined up on.

    The centre line if there is one, because that is the seam traffic is
    arranged around and the one line that must not kink across the patch.
    Failing that the datum, which is where the profile says its own centre
    sits (D4) - not zero, which would be wrong for any widened road.
    """
    for marking in lane_markings(profile):
        if marking.kind is MarkingKind.CENTER_LINE:
            return marking.offset
    return profile.datum


def _entries(
    profile: RoadProfile, flip: float
) -> tuple[list[LaneMarking], list[LaneMarking]]:
    """This profile's markings either side of its anchor, ordered outward.

    A centre line sits *on* the anchor, so it goes into both lists rather than
    neither. That is what makes the case this module exists for come out right:
    a road whose two halves are split by a median meets one whose halves are
    split by a painted line, and the median's two edges each have to run back
    to that single line. Keep it out of both lists and the median simply stops.
    """
    anchor = _anchor(profile)
    shifted = [
        LaneMarking((m.offset - anchor) * flip, m.kind) for m in lane_markings(profile)
    ]
    left = sorted((m for m in shifted if m.offset >= 0.0), key=lambda m: m.offset)
    right = sorted((m for m in shifted if m.offset <= 0.0), key=lambda m: -m.offset)
    return left, right


def _kerbs(profile: RoadProfile, flip: float) -> tuple[float, float]:
    """Where the carriageway ends on each side, in the shared frame.

    Not a marking - a profile with sidewalks paints no edge line - but it is
    the anchor a surplus lane's divider runs out to, because a road that gains
    a lane gains it against the kerb.
    """
    anchor = _anchor(profile)
    lanes = [k for k, lane in enumerate(profile.lanes) if lane.type.carries_vehicles]
    if not lanes:
        return 0.0, 0.0
    left = (profile.edges[min(lanes)] - anchor) * flip
    right = (profile.edges[max(lanes) + 1] - anchor) * flip
    return (left, right) if flip > 0.0 else (right, left)


def _paired_markings(
    profile_a: RoadProfile,
    profile_b: RoadProfile,
    frame_a,
    frame_b,
    flip: float,
    tangent_a: Vec2,
    tangent_b: Vec2,
) -> list[TransitionMarking]:
    anchor_a, anchor_b = _anchor(profile_a), _anchor(profile_b)

    def at_a(offset: float) -> Vec2:
        return frame_a.position + frame_a.normal * (offset + anchor_a)

    def at_b(offset: float) -> Vec2:
        return frame_b.position + frame_b.normal * (offset * flip + anchor_b)

    left_a, right_a = _entries(profile_a, 1.0)
    left_b, right_b = _entries(profile_b, flip)
    kerb_left_a, kerb_right_a = _kerbs(profile_a, 1.0)
    kerb_left_b, kerb_right_b = _kerbs(profile_b, flip)

    out: list[TransitionMarking] = []
    for side_a, side_b, kerb_a, kerb_b in (
        (left_a, left_b, kerb_left_a, kerb_left_b),
        (right_a, right_b, kerb_right_a, kerb_right_b),
    ):
        out.extend(
            _pair_side(side_a, side_b, kerb_a, kerb_b, at_a, at_b, tangent_a, tangent_b)
        )
    return _deduped(out)


def _marking_curve(start: Vec2, tangent_a: Vec2, end: Vec2, tangent_b: Vec2) -> Path:
    """`start` to `end`, tangent to each mouth's own heading - a chord when
    that heading agrees, a bend when it does not."""
    return biarc(start, tangent_a, end, tangent_b) or Path.of(LineSegment(start, end))


def _pair_side(
    side_a, side_b, kerb_a, kerb_b, at_a, at_b, tangent_a: Vec2, tangent_b: Vec2
) -> list[TransitionMarking]:
    """Match line for line outward from the anchor; run the rest out to the kerb.

    Counting outward from the middle is what makes a widening road read
    correctly: the lines nearest the centre are the ones that continue, so line
    `k` from the middle is line `k` on both cross-sections. The surplus belongs
    to a lane that only exists on one side, and a road gains a lane against its
    kerb - so that line tapers to where the kerb is on the narrow side, which
    is exactly where the new lane has no width yet.
    """
    out: list[TransitionMarking] = []
    shared = min(len(side_a), len(side_b))
    for k in range(shared):
        kind = side_b[k].kind if len(side_b) >= len(side_a) else side_a[k].kind
        start, end = at_a(side_a[k].offset), at_b(side_b[k].offset)
        out.append(
            TransitionMarking(
                kind, start, end, _marking_curve(start, tangent_a, end, tangent_b)
            )
        )
    for extra in side_a[shared:]:
        start, end = at_a(extra.offset), at_b(kerb_b)
        out.append(
            TransitionMarking(
                extra.kind,
                start,
                end,
                _marking_curve(start, tangent_a, end, tangent_b),
                True,
            )
        )
    for extra in side_b[shared:]:
        start, end = at_a(kerb_a), at_b(extra.offset)
        out.append(
            TransitionMarking(
                extra.kind,
                start,
                end,
                _marking_curve(start, tangent_a, end, tangent_b),
                True,
            )
        )
    return out


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
        leaving = _lane_count(source.profile, not source_end.at_a)
        arriving = _lane_count(target.profile, target_end.at_a)
        if leaving == 0 or arriving >= leaving:
            continue
        lanes = _group(source.profile, not source_end.at_a)
        outermost = max(lanes, key=lambda k: abs(source.profile.lane_center(k)))
        centre = source.profile.lane_center(outermost)

        # Set back up its own road, so the arrow is read *before* the taper
        # rather than at the point the lane has already run out. Signed by
        # which end this is, since arc length runs A -> B either way.
        away = 1.0 if source_end.at_a else -1.0
        s_at = source.path.clamp_s(
            source.end_s(source_end.at_a) + away * config.TRANSITION_ARROW_SETBACK
        )
        frame = source.path.sample(s_at)
        # `+left` offsets against a normal that points left (D3): a lane left
        # of centre merges right, and the other way round.
        decal = "arrow_merge_left" if centre > 0.0 else "arrow_merge_right"
        out.append(
            TransitionArrow(
                frame.position + frame.normal * centre,
                -source_end.outgoing_dir,
                decal,
                source.profile.lanes[outermost].width,
            )
        )
    return out


def _group(profile: RoadProfile, towards_b: bool) -> tuple[int, ...]:
    return profile.forward_lanes if towards_b else profile.backward_lanes


def _lane_count(profile: RoadProfile, towards_b: bool) -> int:
    return len(_group(profile, towards_b))
