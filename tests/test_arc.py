"""ArcSegment. This is where the project's core bet lives.

`offset` returning another exact arc is what makes lane geometry, asymmetric
profiles and junction trimming possible without resampling or drift.
"""

from __future__ import annotations

import math

import pytest

from roadsim.geometry import ArcSegment, DegenerateOffsetError, Vec2

from .conftest import EXACT, assert_vec

QUARTER = math.pi / 2


def ccw() -> ArcSegment:
    """Quarter circle, radius 10, starting at (10,0) heading +y. Turns left."""
    return ArcSegment(Vec2(0.0, 0.0), 10.0, 0.0, QUARTER)


def cw() -> ArcSegment:
    """Same start, but turning right."""
    return ArcSegment(Vec2(0.0, 0.0), 10.0, 0.0, -QUARTER)


def test_rejects_non_positive_radius():
    with pytest.raises(ValueError):
        ArcSegment(Vec2(0.0, 0.0), 0.0, 0.0, 1.0)


def test_length_is_radius_times_sweep():
    assert abs(ccw().length - 10.0 * QUARTER) <= EXACT
    assert abs(cw().length - 10.0 * QUARTER) <= EXACT


def test_endpoints():
    arc = ccw()
    assert_vec(arc.start.position, Vec2(10.0, 0.0))
    assert_vec(arc.end.position, Vec2(0.0, 10.0))
    assert_vec(cw().end.position, Vec2(0.0, -10.0))


def test_tangent_points_along_travel():
    assert_vec(ccw().start.tangent, Vec2(0.0, 1.0))
    assert_vec(cw().start.tangent, Vec2(0.0, -1.0))


def test_curvature_sign_follows_turn_direction():
    assert abs(ccw().sample(3.0).curvature - 0.1) <= EXACT
    assert abs(cw().sample(3.0).curvature + 0.1) <= EXACT


def test_sampling_is_by_arc_length_not_angle():
    """Equal steps in s must give equal chord lengths all the way round."""
    arc = ccw()
    chords = [
        arc.sample(s).position.distance_to(arc.sample(s + 0.5).position)
        for s in [i * 0.5 for i in range(int(arc.length / 0.5) - 1)]
    ]
    assert max(chords) - min(chords) <= EXACT


@pytest.mark.parametrize("d", [-6.0, -2.5, 2.5, 6.0])
def test_offset_stays_exactly_d_from_the_centreline(d):
    arc = ccw()
    off = arc.offset(d)
    for i in range(21):
        a = arc.sample(arc.length * i / 20).position
        b = off.sample(off.length * i / 20).position
        assert abs(a.distance_to(b) - abs(d)) <= EXACT


def test_offset_left_of_a_left_turn_is_the_inner_edge():
    """A left turn curves toward its left, so the left lane edge is shorter."""
    arc = ccw()
    assert abs(arc.offset(4.0).radius - 6.0) <= EXACT
    assert abs(arc.offset(-4.0).radius - 14.0) <= EXACT


def test_offset_right_of_a_right_turn_is_the_inner_edge():
    arc = cw()
    assert abs(arc.offset(-4.0).radius - 6.0) <= EXACT
    assert abs(arc.offset(4.0).radius - 14.0) <= EXACT


def test_offset_preserves_turn_direction():
    assert ccw().offset(4.0).sweep > 0.0
    assert cw().offset(4.0).sweep < 0.0


def test_offset_beyond_the_radius_is_refused():
    """Better a clear error than a silently inverted lane."""
    with pytest.raises(DegenerateOffsetError):
        ccw().offset(10.0)
    with pytest.raises(DegenerateOffsetError):
        ccw().offset(12.0)


def test_reversed_retraces_the_same_points():
    arc = ccw()
    rev = arc.reversed()
    assert abs(rev.length - arc.length) <= EXACT
    assert_vec(rev.start.position, arc.end.position)
    assert_vec(rev.end.position, arc.start.position)
    assert_vec(rev.start.tangent, -arc.end.tangent)


def test_trimmed_keeps_the_same_circle():
    arc = ccw()
    part = arc.trimmed(2.0, 9.0)
    assert abs(part.length - 7.0) <= EXACT
    assert abs(part.radius - arc.radius) <= EXACT
    assert_vec(part.start.position, arc.sample(2.0).position)
    assert_vec(part.end.position, arc.sample(9.0).position)


def test_project_finds_the_radial_foot():
    arc = ccw()
    inside = arc.sample(5.0).position * 0.5  # same bearing, half the radius
    assert abs(arc.project(inside) - 5.0) <= EXACT


def test_project_clamps_to_the_nearer_end_when_off_the_arc():
    arc = ccw()
    assert abs(arc.project(Vec2(10.0, -3.0))) <= EXACT
    assert abs(arc.project(Vec2(-3.0, 10.0)) - arc.length) <= EXACT


def test_flatten_respects_the_sagitta_tolerance():
    arc = ccw()
    for tol in (1.0, 0.1, 0.001):
        stations = arc.flatten(tol)
        assert stations[0] == 0.0
        assert abs(stations[-1] - arc.length) <= EXACT
        worst = 0.0
        for s0, s1 in zip(stations, stations[1:]):
            mid_chord = (arc.sample(s0).position + arc.sample(s1).position) * 0.5
            worst = max(worst, arc.center.distance_to(mid_chord))
        assert arc.radius - worst <= tol + EXACT


def test_flatten_adds_detail_as_tolerance_tightens():
    arc = ccw()
    assert len(arc.flatten(0.001)) > len(arc.flatten(0.1)) > len(arc.flatten(1.0))


def test_from_tangent_points_is_tangent_to_the_entry_direction():
    entry, direction = Vec2(0.0, 0.0), Vec2(1.0, 0.0)
    for exit_point in (Vec2(10.0, 10.0), Vec2(10.0, -10.0)):
        arc = ArcSegment.from_tangent_points(entry, direction, exit_point, 10.0)
        assert_vec(arc.start.position, entry)
        assert_vec(arc.end.position, exit_point)
        assert abs(arc.start.tangent.cross(direction)) <= EXACT
        assert arc.start.tangent.dot(direction) > 0.0
