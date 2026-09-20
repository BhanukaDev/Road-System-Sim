"""LineSegment: the trivial half of the kernel, but offsets must still be exact."""

from __future__ import annotations

from roadsim.geometry import LineSegment, Vec2

from .conftest import EXACT, assert_vec


def make() -> LineSegment:
    return LineSegment(Vec2(0.0, 0.0), Vec2(30.0, 40.0))


def test_length_and_arc_length_sampling():
    line = make()
    assert abs(line.length - 50.0) <= EXACT
    assert_vec(line.sample(25.0).position, Vec2(15.0, 20.0))


def test_sample_clamps_outside_the_curve():
    line = make()
    assert_vec(line.sample(-10.0).position, line.p0)
    assert_vec(line.sample(999.0).position, line.p1)


def test_zero_curvature():
    assert abs(make().sample(10.0).curvature) <= EXACT


def test_offset_left_is_parallel_and_exactly_d_away():
    line = make()
    for d in (-8.0, -1.5, 3.5, 7.0):
        off = line.offset(d)
        assert abs(off.length - line.length) <= EXACT
        assert abs(off.direction.cross(line.direction)) <= EXACT
        for s in (0.0, 12.5, 50.0):
            a = line.sample(s).position
            b = off.sample(s).position
            assert abs(a.distance_to(b) - abs(d)) <= EXACT
            # Positive d must land on the left-hand side.
            assert (b - a).dot(line.direction.rot90()) * d > 0.0


def test_reversed_swaps_ends_and_flips_tangent():
    line = make()
    rev = line.reversed()
    assert_vec(rev.sample(0.0).position, line.p1)
    assert_vec(rev.sample(0.0).tangent, -line.direction)


def test_trimmed():
    trimmed = make().trimmed(10.0, 40.0)
    assert abs(trimmed.length - 30.0) <= EXACT


def test_project_clamps_to_the_segment():
    line = make()
    assert abs(line.project(Vec2(15.0, 20.0)) - 25.0) <= EXACT
    assert abs(line.project(Vec2(-100.0, -100.0))) <= EXACT
    assert abs(line.project(Vec2(500.0, 500.0)) - line.length) <= EXACT


def test_flatten_is_just_the_endpoints():
    """A straight never needs subdividing, however far you zoom in."""
    assert make().flatten(1e-6) == [0.0, 50.0]
