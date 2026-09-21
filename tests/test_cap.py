"""Dead-end caps: derived from the single segment end at a degree-1 node.

A two-way road's cap is a semicircular bulge exactly as wide as the road,
tangent to both edges; a one-way road's is just a stop line. Neither touches
the carriageway itself - no trim, no width change - so those are asserted here
too.
"""

from __future__ import annotations

from roadsim.geometry import Vec2
from roadsim.road.cap import CapKind, build_cap
from roadsim.road.network import RoadNetwork
from roadsim.road.presets import ONE_WAY_TWO_LANE, RESIDENTIAL_TWO_WAY

from .conftest import EXACT, approx, assert_vec

ORIGIN = Vec2(0.0, 0.0)
EAST = Vec2(60.0, 0.0)


def test_two_way_dead_end_gets_a_turning_head():
    net = RoadNetwork()
    seg = net.connect(ORIGIN, EAST, RESIDENTIAL_TWO_WAY)
    net.rebuild_all()

    node_b = net.node_at(EAST).id
    cap = net.caps[node_b]
    assert cap.kind is CapKind.TURNING_HEAD
    assert cap.segment_id == seg.id
    assert cap.bulge is not None
    assert approx(cap.bulge.radius, RESIDENTIAL_TWO_WAY.total_width / 2.0)


def test_one_way_dead_end_gets_a_terminal_with_no_bulge():
    net = RoadNetwork()
    net.connect(ORIGIN, EAST, ONE_WAY_TWO_LANE)
    net.rebuild_all()

    node_b = net.node_at(EAST).id
    cap = net.caps[node_b]
    assert cap.kind is CapKind.TERMINAL
    assert cap.bulge is None


def test_turning_head_bulge_is_tangent_to_both_edges():
    """The bulge starts exactly at `left` and ends exactly at `right` - the two
    points the carriageway's own edges land on."""
    net = RoadNetwork()
    net.connect(ORIGIN, EAST, RESIDENTIAL_TWO_WAY)
    net.rebuild_all()

    cap = net.caps[net.node_at(EAST).id]
    assert_vec(cap.bulge.sample(0.0).position, cap.left)
    assert_vec(cap.bulge.sample(cap.bulge.length).position, cap.right)


def test_turning_head_bulges_away_from_the_road():
    """Its midpoint sits beyond the road's end, not back over the carriageway."""
    net = RoadNetwork()
    net.connect(ORIGIN, EAST, RESIDENTIAL_TWO_WAY)
    net.rebuild_all()

    cap = net.caps[net.node_at(EAST).id]
    mid = cap.bulge.sample(cap.bulge.length / 2.0).position
    assert mid.x > EAST.x + EXACT


def test_a_dead_end_cap_leaves_no_trim():
    net = RoadNetwork()
    seg = net.connect(ORIGIN, EAST, RESIDENTIAL_TWO_WAY)
    net.rebuild_all()

    assert seg.trim_a == 0.0
    assert seg.trim_b == 0.0


def test_a_through_node_has_no_cap():
    net = RoadNetwork()
    net.connect(ORIGIN, EAST, RESIDENTIAL_TWO_WAY)
    net.connect(EAST, Vec2(120.0, 0.0), RESIDENTIAL_TWO_WAY)
    net.rebuild_all()

    assert net.node_at(EAST).id not in net.caps


def test_connecting_a_second_road_removes_the_cap():
    net = RoadNetwork()
    net.connect(ORIGIN, EAST, RESIDENTIAL_TWO_WAY)
    net.rebuild_all()
    node_b = net.node_at(EAST).id
    assert node_b in net.caps

    net.connect(EAST, Vec2(60.0, 60.0), RESIDENTIAL_TWO_WAY)
    net.rebuild_all()
    assert node_b not in net.caps
    assert node_b in net.junctions


def test_build_cap_at_the_a_end_also_bulges_outward():
    """The other end of a segment - `at_a=True` - takes the opposite sweep sign,
    so it must bulge away from the road in *its* direction too, not the same
    way as the `at_a=False` end."""
    net = RoadNetwork()
    seg = net.connect(ORIGIN, EAST, RESIDENTIAL_TWO_WAY)
    cap = build_cap(seg, at_a=True)

    assert cap.node_id == seg.node_a
    assert_vec(cap.bulge.sample(0.0).position, cap.left)
    assert_vec(cap.bulge.sample(cap.bulge.length).position, cap.right)
    mid = cap.bulge.sample(cap.bulge.length / 2.0).position
    assert mid.x < ORIGIN.x - EXACT
