"""Which lane gets which turn-arrow decal.

A heuristic over lane position, not a model of turn permissions (see the
module docstring) - so the invariants here are about position and direction,
never about what a junction's other arms actually allow.
"""

from __future__ import annotations

from roadsim import config
from roadsim.road.lane import Direction, LaneSpec, LaneType
from roadsim.road.presets import (
    ALLEY,
    AVENUE_FOUR_LANE,
    ONE_WAY_TWO_LANE,
    RESIDENTIAL_TWO_WAY,
)
from roadsim.road.profile import RoadProfile
from roadsim.road.turn_arrows import TurnKind, turn_arrows

_B, _F, _2, _0 = Direction.BACKWARD, Direction.FORWARD, Direction.BOTH, Direction.NONE
CAR = 3.5


def by_lane(profile: RoadProfile) -> dict[int, TurnKind]:
    return {a.lane: a.kind for a in turn_arrows(profile)}


def test_a_lone_lane_each_way_goes_straight_only():
    kinds = by_lane(RESIDENTIAL_TWO_WAY)
    assert set(kinds.values()) == {TurnKind.STRAIGHT}


def test_two_same_direction_lanes_fork_left_and_right():
    kinds = by_lane(ONE_WAY_TWO_LANE)
    assert sorted(kinds.values(), key=lambda k: k.value) == sorted(
        [TurnKind.STRAIGHT_LEFT, TurnKind.STRAIGHT_RIGHT], key=lambda k: k.value
    )


def test_the_median_side_lane_turns_across_oncoming_traffic():
    """Median-adjacent is the passing lane in a real cross-section - it is the
    one the turn *across oncoming traffic* comes off, not the kerb lane.

    Which turn that is, is the whole of handedness: drive on the right and you
    cross oncoming traffic turning left; drive on the left and you cross it
    turning right. Both groups' median-adjacent lane gets the same option,
    because the median is each group's own inner edge.
    """
    across = TurnKind.STRAIGHT_RIGHT if config.DRIVE_ON_LEFT else TurnKind.STRAIGHT_LEFT
    profile = AVENUE_FOUR_LANE
    arrows = {a.lane: a for a in turn_arrows(profile)}
    median_index = next(
        k for k, lane in enumerate(profile.lanes) if lane.type is LaneType.MEDIAN
    )
    assert arrows[median_index - 1].kind is across
    assert arrows[median_index + 1].kind is across


def test_a_middle_lane_among_three_goes_straight_only():
    profile = RoadProfile(
        "triple",
        (
            LaneSpec(CAR, _F, LaneType.CAR),
            LaneSpec(CAR, _F, LaneType.CAR),
            LaneSpec(CAR, _F, LaneType.CAR),
        ),
    )
    kinds = [a.kind for a in turn_arrows(profile)]
    assert kinds == [TurnKind.STRAIGHT_LEFT, TurnKind.STRAIGHT, TurnKind.STRAIGHT_RIGHT]


def test_a_both_direction_lane_gets_an_arrow_each_way():
    arrows = turn_arrows(ALLEY)
    signs = {a.sign for a in arrows}
    assert signs == {1.0, -1.0}
    assert all(a.kind is TurnKind.STRAIGHT for a in arrows)


def test_a_non_traffic_lane_never_gets_an_arrow():
    walk = LaneSpec(2.0, _0, LaneType.SIDEWALK)
    car = LaneSpec(CAR, _F, LaneType.CAR)
    profile = RoadProfile("test", (walk, car, walk))
    assert {a.lane for a in turn_arrows(profile)} == {1}
