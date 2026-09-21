"""Alignment guides.

A guide is a hint, not a snap - these tests are about *when one is offered*,
at a reach measured in pixels like every other on-screen radius (D8).
"""

from __future__ import annotations

import pytest

from roadsim import config
from roadsim.editor.guides import GuideKind, find_guides
from roadsim.geometry import Vec2
from roadsim.render.camera import Camera
from roadsim.road.network import RoadNetwork
from roadsim.road.presets import RESIDENTIAL_TWO_WAY

P = RESIDENTIAL_TWO_WAY


@pytest.fixture
def net() -> RoadNetwork:
    """One node at the origin with a straight arm running east, and a lone
    node with none, for the horizontal/vertical cases."""
    network = RoadNetwork()
    network.connect(Vec2(0.0, 0.0), Vec2(40.0, 0.0), P)
    network.add_node(Vec2(-50.0, 30.0))
    network.rebuild_all()
    return network


def camera(zoom: float = 10.0) -> Camera:
    return Camera(zoom=zoom, viewport=(1440, 900))


def test_a_point_above_a_node_gets_a_vertical_guide(net):
    guides = find_guides(net, camera(), Vec2(0.0, 25.0))
    vertical = [g for g in guides if g.kind is GuideKind.VERTICAL]
    assert any(g.anchor == Vec2(0.0, 0.0) for g in vertical)


def test_a_point_beside_a_node_gets_a_horizontal_guide(net):
    guides = find_guides(net, camera(), Vec2(25.0, 30.0))
    horizontal = [g for g in guides if g.kind is GuideKind.HORIZONTAL]
    assert any(g.anchor == Vec2(-50.0, 30.0) for g in horizontal)


def test_far_from_every_node_yields_no_guides(net):
    assert find_guides(net, camera(), Vec2(300.0, 300.0)) == []


def test_the_reach_is_in_pixels_not_metres(net):
    """The same pixel distance triggers a guide whatever the zoom (D8)."""
    within = (config.ALIGNMENT_GUIDE_PX - 2.0) / 8.0
    assert find_guides(net, camera(zoom=8.0), Vec2(within, 25.0))
    beyond = (config.ALIGNMENT_GUIDE_PX + 4.0) / 8.0
    assert find_guides(net, camera(zoom=8.0), Vec2(beyond, 25.0)) == []


def test_extending_a_straight_arm_gets_an_extension_guide(net):
    """A point further out along the road already leaving the origin node."""
    guides = find_guides(net, camera(), Vec2(80.0, 0.001))
    extension = [g for g in guides if g.kind is GuideKind.EXTENSION]
    assert any(g.anchor == Vec2(0.0, 0.0) for g in extension)


def test_a_point_behind_the_arm_is_not_an_extension(net):
    """West of the origin is behind *its* arm, which runs east - even though it
    is still ahead of the far node's own arm, which runs the other way."""
    guides = find_guides(net, camera(), Vec2(-80.0, 0.001))
    from_origin = [
        g
        for g in guides
        if g.kind is GuideKind.EXTENSION and g.anchor == Vec2(0.0, 0.0)
    ]
    assert not from_origin


def test_nothing_in_an_empty_network():
    empty = RoadNetwork()
    assert find_guides(empty, camera(), Vec2(0.0, 0.0)) == []
