"""Snapping.

The invariant worth defending is the one in the M2 design: snap radii are in
pixels. A snap expressed in metres gets harder to hit the further you zoom out,
which reads as the editor breaking - so most of these tests assert behaviour
*across zoom levels* rather than at one.
"""

from __future__ import annotations

import math

import pytest

from roadsim import config
from roadsim.editor.snapping import SnapKind, Snapper
from roadsim.geometry import Vec2
from roadsim.render.camera import Camera
from roadsim.road.network import RoadNetwork
from roadsim.road.presets import RESIDENTIAL_TWO_WAY

from .conftest import approx, assert_vec

P = RESIDENTIAL_TWO_WAY


@pytest.fixture
def net() -> RoadNetwork:
    network = RoadNetwork()
    network.connect(Vec2(-60.0, 0.0), Vec2(60.0, 0.0), P)
    network.connect(Vec2(0.0, 80.0), Vec2(0.0, 200.0), P)
    network.rebuild_all()
    return network


def snapper(net: RoadNetwork, zoom: float = 10.0) -> Snapper:
    return Snapper(net, Camera(zoom=zoom, viewport=(1440, 900)))


# -- priority --------------------------------------------------------------


def test_a_node_wins_over_the_road_it_sits_on(net):
    """The end node and the road are both under the cursor. The node is what
    the user meant."""
    snap = snapper(net).snap(Vec2(-60.0, 0.2))
    assert snap.kind is SnapKind.NODE
    assert snap.node_id == net.node_at(Vec2(-60.0, 0.0)).id


def test_a_road_wins_over_the_grid(net):
    snap = snapper(net).snap(Vec2(20.0, 0.1))
    assert snap.kind is SnapKind.SEGMENT
    segment_id, s = snap.segment_hit
    assert segment_id == 1
    assert approx(s, 80.0, 1e-6)
    assert_vec(snap.position, Vec2(20.0, 0.0), 1e-6)


def test_open_space_falls_through_to_the_grid(net):
    snap = snapper(net).snap(Vec2(300.0, 301.7))
    assert snap.kind is SnapKind.GRID


def test_the_angle_constraint_only_applies_in_open_space(net):
    """Holding shift must not stop you connecting to a node you are pointing at."""
    snap = snapper(net).snap(
        Vec2(-60.0, 0.1), from_point=Vec2(-200.0, 3.0), constrain_angle=True
    )
    assert snap.kind is SnapKind.NODE


# -- radii are in pixels ---------------------------------------------------


def test_the_snap_radius_grows_in_metres_as_you_zoom_out(net):
    """The same point is out of reach zoomed in and in reach zoomed out,
    because the radius that matters is the one on screen."""
    off_by = Vec2(-60.0, 3.0)
    assert snapper(net, zoom=40.0).snap(off_by).kind is not SnapKind.NODE
    assert snapper(net, zoom=2.0).snap(off_by).kind is SnapKind.NODE


@pytest.mark.parametrize("zoom", [0.5, 2.0, 10.0, 60.0])
def test_a_node_is_reachable_from_the_same_pixel_distance_at_any_zoom(net, zoom):
    """Ten pixels away is ten pixels away, whatever the zoom."""
    snap = snapper(net, zoom)
    ten_px = 10.0 / zoom
    assert snap.snap(Vec2(-60.0, ten_px)).kind is SnapKind.NODE
    beyond = (config.SNAP_NODE_PX + 6.0) / zoom
    assert snap.snap(Vec2(-60.0, beyond)).kind is not SnapKind.NODE


def test_world_radius_is_pixels_over_zoom(net):
    assert approx(snapper(net, zoom=8.0).world_radius(16.0), 2.0)


# -- the grid --------------------------------------------------------------


def test_the_grid_pulls_a_nearby_point_onto_it(net):
    snap = snapper(net, zoom=10.0).snap(Vec2(299.6, 400.3))
    assert snap.kind is SnapKind.GRID
    assert_vec(snap.position, Vec2(300.0, 400.0))


def test_the_grid_leaves_a_point_alone_when_it_is_nowhere_near(net):
    """Zoomed in, the grid is far away on screen and must not drag the point."""
    loose = Vec2(304.0, 405.0)
    snap = snapper(net, zoom=60.0).snap(loose)
    assert snap.kind is SnapKind.GRID
    assert_vec(snap.position, loose)


def test_a_zoomed_out_click_is_not_yanked_across_the_map(net):
    """Grid snapping at low zoom would otherwise move a click tens of metres."""
    loose = Vec2(304.0, 405.0)
    snap = snapper(net, zoom=0.5).snap(loose)
    assert snap.position.distance_to(loose) <= config.GRID_SPACING


# -- the angle constraint --------------------------------------------------


def test_the_angle_constraint_lands_on_a_multiple_of_the_step(net):
    origin = Vec2(400.0, 400.0)
    snap = snapper(net).snap(
        origin + Vec2(50.0, 9.0), from_point=origin, constrain_angle=True
    )
    assert snap.kind is SnapKind.ANGLE
    angle = math.degrees((snap.position - origin).angle)
    assert approx(angle % config.ANGLE_SNAP_DEG, 0.0, 1e-9)


def test_the_angle_constraint_keeps_the_distance_drawn(net):
    origin = Vec2(400.0, 400.0)
    target = origin + Vec2(50.0, 9.0)
    snap = snapper(net).snap(target, from_point=origin, constrain_angle=True)
    assert approx(snap.position.distance_to(origin), target.distance_to(origin))


# -- exclusions ------------------------------------------------------------


def test_a_node_can_be_excluded_so_a_drag_does_not_snap_to_itself(net):
    node = net.node_at(Vec2(-60.0, 0.0))
    snap = snapper(net).snap(Vec2(-60.0, 0.1), ignore_nodes=frozenset({node.id}))
    assert snap.kind is not SnapKind.NODE


def test_a_segment_can_be_excluded(net):
    snap = snapper(net).snap(Vec2(20.0, 0.1), ignore_segments=frozenset({1}))
    assert snap.kind is not SnapKind.SEGMENT


def test_nothing_snaps_in_an_empty_network():
    empty = Snapper(RoadNetwork(), Camera(zoom=10.0))
    assert empty.nearest_node(Vec2(0.0, 0.0)) is None
    assert empty.nearest_segment(Vec2(0.0, 0.0)) is None
    assert empty.snap(Vec2(3.0, 4.0)).kind is SnapKind.GRID
