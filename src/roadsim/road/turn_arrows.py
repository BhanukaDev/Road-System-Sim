"""Which lane gets which turn-arrow decal, at a real junction's stop line.

This is a heuristic read off lane position, exactly like the periodic
direction chevrons already read `direction` and nothing else - it is not a
model of turn permissions. That model is lane-to-lane connectivity, reserved
for M5 (D5); until it exists, an arrow here never claims to know more about
the junction than the profile does, only where a lane sits among its own
same-direction neighbours.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .profile import RoadProfile


class TurnKind(Enum):
    STRAIGHT = "straight"
    LEFT = "left"
    RIGHT = "right"
    STRAIGHT_LEFT = "straight_left"
    STRAIGHT_RIGHT = "straight_right"


@dataclass(frozen=True, slots=True)
class TurnArrow:
    lane: int
    """Index into the profile's own lane list."""
    sign: float
    """+1.0 travels A -> B, -1.0 travels B -> A - which way the decal points."""
    kind: TurnKind


def turn_arrows(profile: RoadProfile) -> tuple[TurnArrow, ...]:
    """One decal per travelling lane, grouped by direction.

    The outermost lane on the driver's left of its own direction group gets
    the left option, the outermost on the right gets the right option, and
    anything in between - or a lone lane - goes straight only.
    """
    out: list[TurnArrow] = []
    groups = (
        (1.0, profile.forward_lanes),
        (-1.0, tuple(reversed(profile.backward_lanes))),
    )
    for sign, group in groups:
        n = len(group)
        for pos, lane in enumerate(group):
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
