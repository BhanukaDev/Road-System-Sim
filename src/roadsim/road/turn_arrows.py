"""Which lane gets which turn-arrow decal, at a real junction's stop line.

This is a heuristic read off lane position, exactly like the periodic
direction chevrons already read `direction` and nothing else - it is not a
model of turn permissions. That model is lane-to-lane connectivity, reserved
for M5 (D5); until it exists, an arrow here never claims to know more about
the junction than the profile does, only where a lane sits among its own
same-direction neighbours.

`available_turns` is the one exception: it reads the junction's own arms to
say whether a left or right turn exists *at all* at this mouth, so a lone lane
or an outer lane does not get painted with an option nothing connects to. That
is still short of connectivity - it never says which lane on the far side a
turn lands in, only that some arm is out there to turn onto.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum

from .. import config
from ..geometry import Vec2
from .crosswalk import approach_lanes
from .junction import Junction
from .profile import RoadProfile


class TurnKind(Enum):
    STRAIGHT = "straight"
    LEFT = "left"
    RIGHT = "right"
    STRAIGHT_LEFT = "straight_left"
    STRAIGHT_RIGHT = "straight_right"
    STRAIGHT_LEFT_RIGHT = "straight_left_right"

    @property
    def decal(self) -> str:
        """The painted shape this option is drawn as (`road/decal.py`).

        A plain mapping rather than a branch in the renderer: adding an option
        is this line and an import, and no renderer learns its name (rule 2).
        """
        return TURN_DECALS[self]


TURN_DECALS: dict[TurnKind, str] = {
    TurnKind.STRAIGHT: "arrow_straight",
    TurnKind.LEFT: "arrow_left",
    TurnKind.RIGHT: "arrow_right",
    TurnKind.STRAIGHT_LEFT: "arrow_straight_left",
    TurnKind.STRAIGHT_RIGHT: "arrow_straight_right",
    TurnKind.STRAIGHT_LEFT_RIGHT: "arrow_straight_left_right",
}


@dataclass(frozen=True, slots=True)
class TurnArrow:
    lane: int
    """Index into the profile's own lane list."""
    sign: float
    """+1.0 travels A -> B, -1.0 travels B -> A - which way the decal points."""
    kind: TurnKind


def arrows_for_mouth(
    profile: RoadProfile, at_a: bool, junction: Junction, segment_id: int
) -> tuple[TurnArrow, ...]:
    """The decals painted at one junction mouth: the approach lanes only.

    A turn decal tells a driver what they may do from the lane they are in, so
    it belongs on the lanes arriving at this mouth and nowhere else. Painting
    every lane puts arrows on the carriageway *leaving* the junction too, where
    they face oncoming drivers who are already past the decision.

    Which options exist comes from `available_turns` - a lane never gets a
    left or right it has nothing to turn onto.
    """
    approaching = set(approach_lanes(profile, at_a))
    left, right = available_turns(junction, segment_id, at_a)
    return tuple(
        a for a in turn_arrows_at_mouth(profile, left, right) if a.lane in approaching
    )


def available_turns(
    junction: Junction, segment_id: int, at_a: bool
) -> tuple[bool, bool]:
    """Whether a real left / right turn exists at this mouth.

    An arm counts only if it bends far enough off straight-ahead to be a turn,
    and not so far that it is this arm's own gore sibling - see
    `config.TURN_ARROW_MIN_ANGLE_DEG` / `TURN_ARROW_MAX_ANGLE_DEG`. `left`/`right`
    are the driver's own, following the same left-is-CCW convention as
    `Vec2.rot90` (D3).
    """
    this = next(
        e for e in junction.ends if e.segment_id == segment_id and e.at_a == at_a
    )
    arriving = -this.outgoing_dir
    lo = math.radians(config.TURN_ARROW_MIN_ANGLE_DEG)
    hi = math.radians(config.TURN_ARROW_MAX_ANGLE_DEG)
    left = right = False
    for other in junction.ends:
        if other.segment_id == this.segment_id and other.at_a == this.at_a:
            continue
        angle = _signed_turn_angle(arriving, other.outgoing_dir)
        if not (lo <= abs(angle) <= hi):
            continue
        if angle > 0.0:
            left = True
        else:
            right = True
    return left, right


def _signed_turn_angle(arriving: Vec2, departing: Vec2) -> float:
    """Angle turned from `arriving` to `departing`, in `(-pi, pi]`.

    Positive is a left turn: CCW is left the same way `Vec2.rot90` is (D3).
    """
    cross = arriving.x * departing.y - arriving.y * departing.x
    return math.atan2(cross, arriving.dot(departing))


def turn_arrows(profile: RoadProfile) -> tuple[TurnArrow, ...]:
    """One decal per travelling lane, grouped by direction.

    The outermost lane on the driver's left of its own direction group gets
    the left option, the outermost on the right gets the right option, and
    anything in between - or a lone lane - goes straight only.

    This has no way to know whether a junction actually offers those turns -
    see `turn_arrows_at_mouth` for the version that does.
    """
    out: list[TurnArrow] = []
    for lane, sign, pos, n in _lane_positions(profile):
        if n <= 1:
            kind = TurnKind.STRAIGHT
        elif pos == 0:
            kind = TurnKind.STRAIGHT_LEFT
        elif pos == n - 1:
            kind = TurnKind.STRAIGHT_RIGHT
        else:
            kind = TurnKind.STRAIGHT
        out.append(TurnArrow(lane, sign, kind))
    return tuple(out)


def turn_arrows_at_mouth(
    profile: RoadProfile, left_available: bool, right_available: bool
) -> tuple[TurnArrow, ...]:
    """`turn_arrows`, gated by which turns this mouth's junction actually offers.

    A lone lane serving every arm gets the combined option for whichever turns
    exist - both, one, or, at a plain through road, neither. An outer lane in a
    multi-lane group only gets its option if that turn exists; otherwise it
    goes straight, same as a middle lane.
    """
    out: list[TurnArrow] = []
    for lane, sign, pos, n in _lane_positions(profile):
        if n <= 1:
            if left_available and right_available:
                kind = TurnKind.STRAIGHT_LEFT_RIGHT
            elif left_available:
                kind = TurnKind.STRAIGHT_LEFT
            elif right_available:
                kind = TurnKind.STRAIGHT_RIGHT
            else:
                kind = TurnKind.STRAIGHT
        elif pos == 0 and left_available:
            kind = TurnKind.STRAIGHT_LEFT
        elif pos == n - 1 and right_available:
            kind = TurnKind.STRAIGHT_RIGHT
        else:
            kind = TurnKind.STRAIGHT
        out.append(TurnArrow(lane, sign, kind))
    return tuple(out)


def _lane_positions(profile: RoadProfile) -> tuple[tuple[int, float, int, int], ...]:
    """`(lane, sign, position in its direction group, group size)`, per lane."""
    groups = (
        (1.0, profile.forward_lanes),
        (-1.0, tuple(reversed(profile.backward_lanes))),
    )
    return tuple(
        (lane, sign, pos, len(group))
        for sign, group in groups
        for pos, lane in enumerate(group)
    )
    return tuple(out)
