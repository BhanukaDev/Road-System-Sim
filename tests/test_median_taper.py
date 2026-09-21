"""A median lane narrowing to a nose approaching a real crossing.

The case this exists for: a median-divided road stopping dead at a crossing's
mouth reads as a slab shoved against the intersection with no transition. Only
a real crossing (3+ arms) earns a taper - a dead end, a straight-through joint
and a two-arm profile transition all keep the median at full width, because
none of them has actually eaten its room the way a crossing has.
"""

from __future__ import annotations

from roadsim import config
from roadsim.geometry import Vec2
from roadsim.road.median_taper import median_tapers
from roadsim.road.network import RoadNetwork
from roadsim.road.presets import AVENUE_FOUR_LANE, RESIDENTIAL_TWO_WAY

from .conftest import approx

ORIGIN = Vec2(0.0, 0.0)


def crossing(profile=AVENUE_FOUR_LANE) -> tuple[RoadNetwork, "RoadSegment"]:
    """A four-way crossing, the median-carrying road running east-west."""
    net = RoadNetwork()
    west_arm = net.connect(Vec2(-90.0, 0.0), ORIGIN, profile)
    net.connect(ORIGIN, Vec2(90.0, 0.0), profile)
    net.connect(Vec2(0.0, -90.0), ORIGIN, RESIDENTIAL_TWO_WAY)
    net.connect(ORIGIN, Vec2(0.0, 90.0), RESIDENTIAL_TWO_WAY)
    net.rebuild_all()
    return net, west_arm


def _tapers(net: RoadNetwork, segment_id: int):
    segment = net.segments[segment_id]
    return median_tapers(
        segment,
        net.junctions.get(segment.node_a),
        net.junctions.get(segment.node_b),
    )


def test_a_median_narrows_approaching_a_real_crossing():
    net, west_arm = crossing()
    tapers = _tapers(net, west_arm.id)
    assert tapers, "a median at a real crossing should get a taper"


def test_a_dead_end_keeps_the_median_at_full_width():
    net = RoadNetwork()
    seg = net.connect(Vec2(-90.0, 0.0), ORIGIN, AVENUE_FOUR_LANE)
    net.rebuild_all()
    assert _tapers(net, seg.id) == ()


def test_a_straight_through_joint_keeps_the_median_at_full_width():
    """Two ends of the same profile running straight through build no
    `Junction` at all (`build_junction`'s through-joint case) - nothing here
    should invent a taper where there is nothing to taper towards."""
    net = RoadNetwork()
    seg_a = net.connect(Vec2(-90.0, 0.0), ORIGIN, AVENUE_FOUR_LANE)
    seg_b = net.connect(ORIGIN, Vec2(90.0, 0.0), AVENUE_FOUR_LANE)
    net.rebuild_all()
    assert net.node_at(ORIGIN).id not in net.junctions
    assert _tapers(net, seg_a.id) == ()
    assert _tapers(net, seg_b.id) == ()


def test_a_two_arm_profile_transition_keeps_the_median_at_full_width():
    """Two arms of different profiles is a lane-count transition
    (`Junction` but not `is_crossing`), which already has its own way of
    carrying paint across the patch (`road/transition.py`) - not a crossing
    a median needs to taper towards."""
    net = RoadNetwork()
    seg = net.connect(Vec2(-90.0, 0.0), ORIGIN, AVENUE_FOUR_LANE)
    net.connect(ORIGIN, Vec2(90.0, 0.0), RESIDENTIAL_TWO_WAY)
    net.rebuild_all()
    node = net.node_at(ORIGIN).id
    assert node in net.junctions
    assert not net.junctions[node].is_crossing
    assert _tapers(net, seg.id) == ()


def test_the_island_reaches_the_nose_width_at_the_mouth():
    net, west_arm = crossing()
    (taper,) = _tapers(net, west_arm.id)
    full_left, nose_left, nose_right, full_right = taper.island
    lane_width = west_arm.profile.lanes[taper.lane_index].width
    nose_width = min(config.MEDIAN_NOSE_WIDTH, lane_width)
    assert approx(full_left.distance_to(full_right), lane_width, 1e-6)
    assert approx(nose_left.distance_to(nose_right), nose_width, 1e-6)


def test_the_taper_never_eats_more_than_its_budget_of_a_short_arm():
    """A short arm cannot lose more than `MEDIAN_TAPER_MAX_FRACTION` of its own
    carriageway to the taper - the same reasoning `_trim_budget` uses for a
    junction's own trim."""
    net = RoadNetwork()
    seg = net.connect(Vec2(-20.0, 0.0), ORIGIN, AVENUE_FOUR_LANE)
    net.connect(ORIGIN, Vec2(90.0, 0.0), AVENUE_FOUR_LANE, via=[Vec2(45.0, 30.0)])
    net.connect(Vec2(0.0, -90.0), ORIGIN, RESIDENTIAL_TWO_WAY)
    net.rebuild_all()
    tapers = _tapers(net, seg.id)
    for taper in tapers:
        length = abs(taper.full_s - seg.end_s(taper.at_a))
        assert (
            length <= seg.carriageway_length * config.MEDIAN_TAPER_MAX_FRACTION + 1e-6
        )
