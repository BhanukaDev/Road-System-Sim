"""`road/validate.py`: reading a network's own verdict on whether it can be
built, plus the one thing it cannot yet say about itself - a crossing with no
node there."""

from __future__ import annotations

import pytest

from roadsim.geometry import Vec2
from roadsim.road.network import RoadNetwork
from roadsim.road.presets import ASYMMETRIC_BOULEVARD, RESIDENTIAL_TWO_WAY
from roadsim.road.validate import check, crossing_problem

from .conftest import assert_vec


@pytest.fixture
def network() -> RoadNetwork:
    network = RoadNetwork()
    network.connect(Vec2(-60.0, 0.0), Vec2(60.0, 0.0), RESIDENTIAL_TWO_WAY)
    network.rebuild_all()
    return network


def _all(network: RoadNetwork):
    return frozenset(network.segments), frozenset(network.nodes)


def test_a_sound_network_has_no_problem(network):
    assert check(network, *_all(network)) is None


def test_a_road_drawn_through_another_is_a_crossing_at_the_exact_point(network):
    spur = network.connect(Vec2(10.0, -40.0), Vec2(10.0, 40.0), RESIDENTIAL_TWO_WAY)
    network.rebuild_all()

    problem = crossing_problem(network, spur)
    assert problem is not None
    assert "crosses" in problem.reason
    assert_vec(problem.position, Vec2(10.0, 0.0))


def test_meeting_at_a_shared_node_is_not_a_crossing(network):
    end = network.node_at(Vec2(60.0, 0.0))
    spur = network.connect(end.position, Vec2(60.0, 50.0), RESIDENTIAL_TWO_WAY)
    network.rebuild_all()
    assert crossing_problem(network, spur) is None
    assert check(network, *_all(network)) is None


def test_a_t_junction_formed_by_splitting_is_not_a_crossing(network):
    network.split_segment(1, 60.0)
    mid = network.node_at(Vec2(0.0, 0.0))
    spur = network.connect(mid.position, Vec2(0.0, 50.0), RESIDENTIAL_TWO_WAY)
    network.rebuild_all()
    assert crossing_problem(network, spur) is None


def test_only_new_roads_are_asked_about_crossings(network):
    """An existing tangle is not this change's fault - a preview elsewhere
    must not go red for it."""
    network.connect(Vec2(10.0, -40.0), Vec2(10.0, 40.0), RESIDENTIAL_TWO_WAY)
    fresh = network.connect(Vec2(0.0, 80.0), Vec2(40.0, 80.0), RESIDENTIAL_TWO_WAY)
    network.rebuild_all()
    scope = frozenset({fresh.id}), frozenset({fresh.node_a, fresh.node_b})
    assert check(network, *scope, frozenset({fresh.id})) is None


def test_a_curve_too_tight_for_its_width_is_reported_at_the_road(network):
    wide = network.connect(
        Vec2(0.0, 40.0),
        Vec2(30.0, 40.0),
        ASYMMETRIC_BOULEVARD,
        via=[Vec2(15.0, 100.0)],
        corner_radius=2.0,
    )
    network.rebuild_all()
    assert wide.is_degenerate
    problem = check(network, frozenset({wide.id}), frozenset())
    assert problem is not None
    assert "too tight" in problem.reason
    assert problem.position is not None


def test_a_road_crossing_itself_is_reported(network):
    knot = network.connect(
        Vec2(0.0, 40.0),
        Vec2(0.0, 100.0),
        RESIDENTIAL_TWO_WAY,
        via=[Vec2(60.0, 40.0), Vec2(60.0, 100.0), Vec2(-20.0, 70.0), Vec2(30.0, 70.0)],
    )
    network.rebuild_all()
    problem = crossing_problem(network, knot)
    assert problem is not None
    assert "itself" in problem.reason
