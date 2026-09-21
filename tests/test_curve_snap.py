"""Alt's three snaps, as pure functions of geometry.

No pygame anywhere in `curve_snap.py`, so every case here is a direct call -
no window, no mouse, no modifier key. `tests/test_shape_road_tool.py` proves
the wiring (an explicit `alt` argument into `ShapeRoadTool.drag_to`, never a
live `pygame.key.get_mods()` read outside `handle_event`); this file proves
the maths.
"""

from __future__ import annotations

import math

import pytest

from roadsim.editor.curve_snap import (
    SnapRequest,
    heading_quantise,
    round_radius,
    snap_curve,
    tangent_continuity,
)
from roadsim.geometry import Vec2
from roadsim.geometry.fillet import MIN_RADIUS
from roadsim.road.network import RoadNetwork
from roadsim.road.presets import RESIDENTIAL_TWO_WAY
from roadsim.serialization import dumps

from .conftest import EXACT, assert_vec

ORIGIN = Vec2(0.0, 0.0)


# -- tangent_continuity -------------------------------------------------


def test_tangent_continuity_lands_exactly_on_the_continuing_ray():
    """B runs east from the shared node; continuing straight through means A
    should leave the node running west - the opposite direction, not B's own."""
    net = RoadNetwork()
    net.connect(ORIGIN, Vec2(100.0, 0.0), RESIDENTIAL_TWO_WAY)  # arm B, east
    seg_a = net.connect(
        ORIGIN, Vec2(-30.0, 80.0), RESIDENTIAL_TWO_WAY, via=[Vec2(-10.0, 40.0)]
    )

    req = SnapRequest(net, seg_a, list(seg_a.control_points), 1, Vec2(-10.0, 60.0))
    hit = tangent_continuity(req)

    assert hit is not None
    anchor, line = ORIGIN, Vec2(-1.0, 0.0)
    assert abs((hit.position - anchor).cross(line)) <= EXACT
    assert hit.readout == "tangent"


def test_applying_tangent_continuity_removes_the_kink():
    net = RoadNetwork()
    seg_b = net.connect(ORIGIN, Vec2(100.0, 0.0), RESIDENTIAL_TWO_WAY)
    seg_a = net.connect(
        ORIGIN, Vec2(-30.0, 80.0), RESIDENTIAL_TWO_WAY, via=[Vec2(-10.0, 40.0)]
    )

    req = SnapRequest(net, seg_a, list(seg_a.control_points), 1, Vec2(-10.0, 60.0))
    hit = tangent_continuity(req)
    points = list(seg_a.control_points)
    points[1] = hit.position
    net.set_control_points(seg_a.id, points)

    seg_a = net.segments[seg_a.id]
    assert_vec(seg_a.outgoing_dir(True), -seg_b.outgoing_dir(True))


def test_tangent_continuity_only_applies_next_to_a_node_end():
    net = RoadNetwork()
    net.connect(ORIGIN, Vec2(100.0, 0.0), RESIDENTIAL_TWO_WAY)
    seg_a = net.connect(
        Vec2(-90.0, -30.0),
        Vec2(95.0, -25.0),
        RESIDENTIAL_TWO_WAY,
        via=[Vec2(-10.0, 20.0), Vec2(30.0, 25.0), Vec2(45.0, -20.0)],
    )

    middle_index = 2  # nowhere near either end of a 5-point list
    req = SnapRequest(
        net, seg_a, list(seg_a.control_points), middle_index, Vec2(30.0, 40.0)
    )
    assert tangent_continuity(req) is None


def test_tangent_continuity_needs_another_arm_at_the_node():
    """A dead end has nothing else to line up with."""
    net = RoadNetwork()
    seg_a = net.connect(
        ORIGIN, Vec2(-30.0, 80.0), RESIDENTIAL_TWO_WAY, via=[Vec2(-10.0, 40.0)]
    )
    req = SnapRequest(net, seg_a, list(seg_a.control_points), 1, Vec2(-10.0, 60.0))
    assert tangent_continuity(req) is None


# -- heading_quantise -----------------------------------------------------


def test_heading_quantise_snaps_both_legs_to_the_angle_step():
    points = [Vec2(-40.0, 0.0), Vec2(0.0, 0.0), Vec2(40.0, 30.0)]
    req = SnapRequest(None, None, points, 1, Vec2(3.0, 22.0))

    hit = heading_quantise(req)
    assert hit is not None

    prev, nxt = points[0], points[2]
    step = math.radians(15.0)
    into_angle = (hit.position - prev).angle
    out_angle = (nxt - hit.position).angle
    assert abs(math.remainder(into_angle, step)) <= EXACT
    assert abs(math.remainder(out_angle, step)) <= EXACT


def test_heading_quantise_deflection_is_a_multiple_of_the_step():
    points = [Vec2(-40.0, 0.0), Vec2(0.0, 0.0), Vec2(40.0, 30.0)]
    req = SnapRequest(None, None, points, 1, Vec2(3.0, 22.0))
    hit = heading_quantise(req)

    prev, nxt = points[0], points[2]
    into = (hit.position - prev).angle
    out = (nxt - hit.position).angle
    turn = math.degrees(abs(out - into))
    assert abs(math.remainder(turn, 15.0)) <= 1e-6


def test_heading_quantise_none_for_parallel_legs():
    """Both legs already point due east - quantised, they stay parallel and
    two parallel rays have no intersection to snap to."""
    points = [Vec2(0.0, 0.0), Vec2(40.0, 0.001), Vec2(80.0, 0.0)]
    req = SnapRequest(None, None, points, 1, Vec2(40.0, 0.001))
    assert heading_quantise(req) is None


def test_heading_quantise_none_behind_the_ray():
    """Dragged past `nxt`, the quantised rays cross exactly at `nxt` itself -
    a zero-length result, correctly rejected as behind rather than returned
    as a degenerate snap."""
    points = [Vec2(0.0, 0.0), Vec2(100.0, 0.0), Vec2(200.0, 0.0)]
    req = SnapRequest(None, None, points, 1, Vec2(120.0, 5.0))
    assert heading_quantise(req) is None


def test_heading_quantise_only_applies_to_interior_indices():
    points = [Vec2(0.0, 0.0), Vec2(40.0, 0.0)]
    assert heading_quantise(SnapRequest(None, None, points, 0, Vec2(0.0, 0.0))) is None
    assert heading_quantise(SnapRequest(None, None, points, 1, Vec2(0.0, 0.0))) is None


# -- round_radius ----------------------------------------------------------


def test_round_radius_is_idempotent_on_every_rung():
    from roadsim import config

    for rung in config.RADIUS_LADDER:
        assert round_radius(rung) == pytest.approx(rung, abs=1e-9)


def test_round_radius_is_monotonic():
    from roadsim import config

    raws = [1.0, 6.0, 9.0, 18.0, 35.0, 60.0, 90.0]
    results = [round_radius(r) for r in raws]
    assert results == sorted(results)
    assert results[-1] <= config.RADIUS_LADDER[-1]


def test_round_radius_never_goes_below_min_radius():
    assert round_radius(0.0) >= MIN_RADIUS
    assert round_radius(-5.0) >= MIN_RADIUS


# -- precedence: tangent beats heading quantisation (D19) --------------------


def test_snap_curve_prefers_tangent_continuity_when_both_apply():
    net = RoadNetwork()
    net.connect(ORIGIN, Vec2(100.0, 0.0), RESIDENTIAL_TWO_WAY)  # the other arm
    seg_a = net.connect(
        ORIGIN,
        Vec2(-60.0, 80.0),
        RESIDENTIAL_TWO_WAY,
        via=[Vec2(-20.0, 30.0), Vec2(-40.0, 55.0)],
    )

    points = list(seg_a.control_points)
    target = Vec2(-15.0, 42.0)  # off both the tangent ray and a tidy angle
    req = SnapRequest(net, seg_a, points, 1, target)

    tangent_hit = tangent_continuity(req)
    angle_hit = heading_quantise(req)
    assert tangent_hit is not None and angle_hit is not None
    assert tangent_hit.position != angle_hit.position  # the two genuinely disagree

    result = snap_curve(req)
    assert result == tangent_hit


def test_snap_curve_falls_back_to_heading_quantise():
    """No other arm at the node, so tangent continuity has nothing to offer -
    the angle grid is what is left."""
    net = RoadNetwork()
    seg_a = net.connect(
        Vec2(-90.0, -30.0),
        Vec2(95.0, -25.0),
        RESIDENTIAL_TWO_WAY,
        via=[Vec2(-10.0, 20.0), Vec2(30.0, 25.0), Vec2(45.0, -20.0)],
    )
    points = list(seg_a.control_points)
    req = SnapRequest(net, seg_a, points, 2, Vec2(28.0, 27.0))

    assert tangent_continuity(req) is None
    assert snap_curve(req) == heading_quantise(req)


def test_snap_curve_is_pure():
    net = RoadNetwork()
    net.connect(ORIGIN, Vec2(100.0, 0.0), RESIDENTIAL_TWO_WAY)
    seg_a = net.connect(
        ORIGIN, Vec2(-30.0, 80.0), RESIDENTIAL_TWO_WAY, via=[Vec2(-10.0, 40.0)]
    )
    net.rebuild_all()
    before = dumps(net)

    req = SnapRequest(net, seg_a, list(seg_a.control_points), 1, Vec2(-10.0, 60.0))
    snap_curve(req)

    assert dumps(net) == before
