"""Lane-aware snap anchors: one per vehicle lane, at each segment end.

An anchor is an alignment aid (D5), so what matters is that its position sits
exactly on that lane's own centreline and its direction continues the road -
never that it forms any new topology.
"""

from __future__ import annotations

from roadsim.geometry import Vec2
from roadsim.road.anchor import end_anchors, node_anchors
from roadsim.road.network import RoadNetwork
from roadsim.road.presets import RESIDENTIAL_TWO_WAY

from .conftest import assert_vec

ORIGIN = Vec2(0.0, 0.0)
EAST = Vec2(60.0, 0.0)


def test_only_vehicle_lanes_get_an_anchor():
    net = RoadNetwork()
    seg = net.connect(ORIGIN, EAST, RESIDENTIAL_TWO_WAY)
    anchors = end_anchors(seg, at_a=False)

    assert len(anchors) == 2  # the two car lanes; both sidewalks skipped
    assert {a.lane for a in anchors} == {1, 2}


def test_an_anchor_sits_on_its_own_lane_centreline():
    net = RoadNetwork()
    seg = net.connect(ORIGIN, EAST, RESIDENTIAL_TWO_WAY)
    by_lane = {a.lane: a for a in end_anchors(seg, at_a=False)}

    assert_vec(by_lane[1].origin, EAST + Vec2(0.0, 1.75))
    assert_vec(by_lane[2].origin, EAST + Vec2(0.0, -1.75))


def test_an_anchor_points_away_from_the_road():
    net = RoadNetwork()
    seg = net.connect(ORIGIN, EAST, RESIDENTIAL_TWO_WAY)

    end = end_anchors(seg, at_a=False)[0]
    assert_vec(end.direction, Vec2(1.0, 0.0))
    start = end_anchors(seg, at_a=True)[0]
    assert_vec(start.direction, Vec2(-1.0, 0.0))


def test_point_at_extends_along_the_anchors_own_direction():
    net = RoadNetwork()
    seg = net.connect(ORIGIN, EAST, RESIDENTIAL_TWO_WAY)
    anchor = end_anchors(seg, at_a=False)[0]

    assert_vec(anchor.point_at(10.0), anchor.origin + Vec2(10.0, 0.0))


def test_node_anchors_gathers_every_end_meeting_a_node():
    net = RoadNetwork()
    net.connect(ORIGIN, EAST, RESIDENTIAL_TWO_WAY)
    net.connect(EAST, Vec2(60.0, 60.0), RESIDENTIAL_TWO_WAY)

    node_id = net.node_at(EAST).id
    anchors = node_anchors(net, node_id)
    assert len(anchors) == 4  # two lanes from each of the two arms
