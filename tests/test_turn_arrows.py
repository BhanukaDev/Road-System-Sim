"""Which lane gets which turn-arrow decal.

A heuristic over lane position, not a model of turn permissions (see the
module docstring) - so the invariants here are about position and direction,
never about what a junction's other arms actually allow, except for
`available_turns` itself, which is exactly that question.
"""

from __future__ import annotations

from roadsim import config
from roadsim.geometry import Vec2
from roadsim.road.lane import Direction, LaneSpec, LaneType
from roadsim.road.network import RoadNetwork
from roadsim.road.presets import (
    ALLEY,
    AVENUE_FOUR_LANE,
    ONE_WAY_TWO_LANE,
    RESIDENTIAL_TWO_WAY,
)
from roadsim.road.profile import RoadProfile
from roadsim.road.turn_arrows import (
    TurnKind,
    arrows_for_mouth,
    available_turns,
    turn_arrows,
    turn_arrows_at_mouth,
)

_B, _F, _2, _0 = Direction.BACKWARD, Direction.FORWARD, Direction.BOTH, Direction.NONE
CAR = 3.5
ORIGIN = Vec2(0.0, 0.0)


def by_lane(profile: RoadProfile) -> dict[int, TurnKind]:
    return {a.lane: a.kind for a in turn_arrows(profile)}


def _mouth(net: RoadNetwork, direction: Vec2) -> tuple[int, bool]:
    """The `(segment_id, at_a)` of the arm leaving the origin in `direction`."""
    hub = net.node_at(ORIGIN).id
    for segment, at_a in net.segments_at(hub):
        if segment.outgoing_dir(at_a).dot(direction) > 0.9:
            return segment.id, at_a
    raise AssertionError(f"no arm leaving {direction}")


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


# -- geometry-gated availability, at a real junction ------------------------


def _square_crossing() -> RoadNetwork:
    """Four arms meeting at the origin at right angles."""
    net = RoadNetwork()
    net.connect(Vec2(-70.0, 0.0), ORIGIN, RESIDENTIAL_TWO_WAY)
    net.connect(ORIGIN, Vec2(70.0, 0.0), RESIDENTIAL_TWO_WAY)
    net.connect(Vec2(0.0, -70.0), ORIGIN, RESIDENTIAL_TWO_WAY)
    net.connect(ORIGIN, Vec2(0.0, 70.0), RESIDENTIAL_TWO_WAY)
    net.rebuild_all()
    return net


def test_a_perpendicular_crossing_offers_both_turns_on_every_arm():
    net = _square_crossing()
    junction = net.junctions[net.node_at(ORIGIN).id]
    for direction in (Vec2(-1.0, 0.0), Vec2(1.0, 0.0), Vec2(0.0, -1.0), Vec2(0.0, 1.0)):
        segment_id, at_a = _mouth(net, direction)
        assert available_turns(junction, segment_id, at_a) == (True, True)


def test_a_t_junction_offers_only_the_turn_that_exists():
    """West -> east is the through road; south is the stem.

    Approaching from the west (heading east), only the stem to the south is a
    turn, and it is a right - there is no arm to the left because there is no
    north arm at all.
    """
    net = RoadNetwork()
    net.connect(Vec2(-70.0, 0.0), ORIGIN, RESIDENTIAL_TWO_WAY)
    net.connect(ORIGIN, Vec2(70.0, 0.0), RESIDENTIAL_TWO_WAY)
    net.connect(Vec2(0.0, -70.0), ORIGIN, RESIDENTIAL_TWO_WAY)
    net.rebuild_all()
    junction = net.junctions[net.node_at(ORIGIN).id]

    segment_id, at_a = _mouth(net, Vec2(-1.0, 0.0))
    assert available_turns(junction, segment_id, at_a) == (False, True)

    segment_id, at_a = _mouth(net, Vec2(0.0, -1.0))
    assert available_turns(junction, segment_id, at_a) == (True, True)


def test_turn_arrows_at_mouth_combines_both_options_for_a_lone_lane():
    kinds = {
        a.kind
        for a in turn_arrows_at_mouth(
            RESIDENTIAL_TWO_WAY, left_available=True, right_available=True
        )
    }
    assert kinds == {TurnKind.STRAIGHT_LEFT_RIGHT}


def test_turn_arrows_at_mouth_falls_back_to_straight_with_no_turns():
    kinds = {
        a.kind
        for a in turn_arrows_at_mouth(
            RESIDENTIAL_TWO_WAY, left_available=False, right_available=False
        )
    }
    assert kinds == {TurnKind.STRAIGHT}


def test_turn_arrows_at_mouth_withholds_an_unavailable_side_on_a_wide_road():
    kinds = {
        a.kind
        for a in turn_arrows_at_mouth(
            ONE_WAY_TWO_LANE, left_available=False, right_available=True
        )
    }
    assert kinds == {TurnKind.STRAIGHT, TurnKind.STRAIGHT_RIGHT}


def test_arrows_for_mouth_reads_the_junction_it_is_given():
    net = _square_crossing()
    junction = net.junctions[net.node_at(ORIGIN).id]
    segment_id, at_a = _mouth(net, Vec2(0.0, 1.0))
    segment = net.segments[segment_id]
    arrows = arrows_for_mouth(segment.profile, at_a, junction, segment_id)
    assert {a.kind for a in arrows} == {TurnKind.STRAIGHT_LEFT_RIGHT}
