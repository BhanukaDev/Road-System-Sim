"""Crosswalks and stop lines, at a real junction's mouths only.

Built on the same four-way fixture `test_pavement.py` uses - a crossing is
where these get exercised for real.
"""

from __future__ import annotations

from roadsim.geometry import Vec2
from roadsim.road.crosswalk import crosswalk_mark
from roadsim.road.lane import Direction, LaneSpec, LaneType
from roadsim.road.network import RoadNetwork
from roadsim.road.presets import ONE_WAY_TWO_LANE, RAIL_DOUBLE, RESIDENTIAL_TWO_WAY
from roadsim.road.profile import RoadProfile

from .conftest import approx

ORIGIN = Vec2(0.0, 0.0)


def crossing(
    east_west=RESIDENTIAL_TWO_WAY, north_south=RESIDENTIAL_TWO_WAY
) -> RoadNetwork:
    net = RoadNetwork()
    net.connect(Vec2(-70.0, 0.0), ORIGIN, east_west)
    net.connect(ORIGIN, Vec2(70.0, 0.0), east_west)
    net.connect(Vec2(0.0, -70.0), ORIGIN, north_south)
    net.connect(ORIGIN, Vec2(0.0, 70.0), north_south)
    net.rebuild_all()
    return net


def test_the_stop_line_sits_further_from_the_mouth_than_the_stripes():
    net = crossing()
    hub = net.node_at(ORIGIN).id
    for segment, at_a in net.segments_at(hub):
        mark = crosswalk_mark(segment, at_a)
        assert mark is not None
        mouth = segment.trim_a if at_a else segment.path.length - segment.trim_b
        stripe_at_mouth = mark.stripes_s0 if at_a else mark.stripes_s1
        assert approx(stripe_at_mouth, mouth)
        away = 1.0 if at_a else -1.0
        assert away * (mark.stop_s - mouth) > away * (stripe_at_mouth - mouth)


def test_the_span_excludes_the_outer_sidewalks():
    net = crossing()
    hub = net.node_at(ORIGIN).id
    segment, at_a = next(iter(net.segments_at(hub)))
    mark = crosswalk_mark(segment, at_a)
    profile = segment.profile
    assert approx(mark.left, profile.edges[1])  # first non-sidewalk lane
    assert approx(mark.right, profile.edges[-2])


def test_a_two_arm_joint_gets_no_crosswalk():
    """Two ends of one profile running straight through is not an intersection -
    `build_junction` returns `None` for it, so there is nothing to iterate."""
    net = RoadNetwork()
    net.connect(Vec2(-70.0, 0.0), ORIGIN, RESIDENTIAL_TWO_WAY)
    net.connect(ORIGIN, Vec2(70.0, 0.0), RESIDENTIAL_TWO_WAY)
    net.rebuild_all()
    assert net.node_at(ORIGIN).id not in net.junctions


def test_a_profile_with_shoulders_instead_of_sidewalks_still_gets_a_span():
    net = crossing(north_south=RAIL_DOUBLE)
    hub = net.node_at(ORIGIN).id
    for segment, at_a in net.segments_at(hub):
        if segment.profile is RAIL_DOUBLE:
            assert crosswalk_mark(segment, at_a) is not None


def test_an_all_sidewalk_profile_has_no_paved_span():
    walk = LaneSpec(2.0, Direction.NONE, LaneType.SIDEWALK)
    profile = RoadProfile("footpath", (walk, walk))
    net = crossing(north_south=RESIDENTIAL_TWO_WAY)
    hub = net.node_at(ORIGIN).id
    segment, at_a = next(iter(net.segments_at(hub)))
    segment.profile = profile
    assert crosswalk_mark(segment, at_a) is None


def test_a_too_short_carriageway_is_skipped_rather_than_overlapping_the_mouth():
    net = RoadNetwork()
    net.connect(Vec2(-3.0, 0.0), ORIGIN, ONE_WAY_TWO_LANE)
    net.connect(ORIGIN, Vec2(3.0, 0.0), ONE_WAY_TWO_LANE)
    net.connect(Vec2(0.0, -70.0), ORIGIN, ONE_WAY_TWO_LANE)
    net.connect(ORIGIN, Vec2(0.0, 70.0), ONE_WAY_TWO_LANE)
    net.rebuild_all()
    hub = net.node_at(ORIGIN).id
    for segment, at_a in net.segments_at(hub):
        if segment.is_too_short:
            assert crosswalk_mark(segment, at_a) is None
