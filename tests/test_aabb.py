"""Bounds. The cheap "no" in front of every expensive query.

A box is only allowed to be a rejection test if it is a true bound, so these
assert both halves: it contains the whole curve, and shrinking it breaks that.
Soundness alone would pass for a box the size of the world.
"""

from __future__ import annotations

import math

import pytest

from roadsim.geometry import Aabb, ArcSegment, LineSegment, Vec2, curve_bounds, path_bounds

from .conftest import EXACT, approx, assert_vec

SAMPLES = 10_000


def contains_all(box: Aabb, curve, samples: int = 2000) -> bool:
    return all(
        box.contains(curve.sample(curve.length * i / samples).position)
        for i in range(samples + 1)
    )


# -- the box itself --------------------------------------------------------


def test_of_takes_the_extremes_of_its_points():
    box = Aabb.of(Vec2(3.0, -2.0), Vec2(-5.0, 8.0), Vec2(1.0, 1.0))
    assert_vec(box.min, Vec2(-5.0, -2.0))
    assert_vec(box.max, Vec2(3.0, 8.0))


def test_of_needs_a_point():
    with pytest.raises(ValueError):
        Aabb.of()


def test_centre_and_size_are_derived():
    box = Aabb.of(Vec2(0.0, 0.0), Vec2(10.0, 4.0))
    assert_vec(box.center, Vec2(5.0, 2.0))
    assert_vec(box.size, Vec2(10.0, 4.0))


def test_touching_boxes_intersect():
    """A rejection test that drops a contact is worse than no rejection test."""
    left = Aabb.of(Vec2(0.0, 0.0), Vec2(5.0, 5.0))
    right = Aabb.of(Vec2(5.0, 0.0), Vec2(10.0, 5.0))
    assert left.intersects(right) and right.intersects(left)


def test_separated_boxes_do_not_intersect():
    left = Aabb.of(Vec2(0.0, 0.0), Vec2(5.0, 5.0))
    away = Aabb.of(Vec2(5.001, 0.0), Vec2(10.0, 5.0))
    assert not left.intersects(away)
    assert not away.intersects(left)


def test_expanding_and_shrinking_move_every_side():
    box = Aabb.of(Vec2(0.0, 0.0), Vec2(10.0, 10.0))
    grown = box.expanded(2.0)
    assert_vec(grown.min, Vec2(-2.0, -2.0))
    assert_vec(grown.max, Vec2(12.0, 12.0))
    assert_vec(box.expanded(-1.0).min, Vec2(1.0, 1.0))


def test_union_covers_both():
    a = Aabb.of(Vec2(0.0, 0.0), Vec2(2.0, 2.0))
    b = Aabb.of(Vec2(-3.0, 5.0), Vec2(-1.0, 6.0))
    union = a.union(b)
    for box in (a, b):
        assert union.contains(box.min) and union.contains(box.max)


# -- curves ----------------------------------------------------------------


def test_a_line_is_bounded_by_its_ends():
    line = LineSegment(Vec2(-4.0, 9.0), Vec2(6.0, -1.0))
    box = curve_bounds(line)
    assert_vec(box.min, Vec2(-4.0, -1.0))
    assert_vec(box.max, Vec2(6.0, 9.0))


def test_a_quarter_arc_is_bounded_by_its_ends_alone():
    """Its sweep reaches no axis extreme, so the endpoints are the whole box -
    a box padded out to the full circle would reject nothing useful."""
    arc = ArcSegment(Vec2(0.0, 0.0), 10.0, 0.0, math.pi / 2.0)
    box = curve_bounds(arc)
    assert_vec(box.min, Vec2(0.0, 0.0))
    assert_vec(box.max, Vec2(10.0, 10.0))


def test_an_arc_box_catches_the_bulge_between_its_ends():
    """The endpoints of this sweep sit at the same height; the arc rises above
    both. A box built from samples can miss that; a closed-form one cannot."""
    arc = ArcSegment(Vec2(0.0, 0.0), 10.0, math.radians(45.0), math.radians(90.0))
    box = curve_bounds(arc)
    assert approx(box.max.y, 10.0)  # the top of the circle is inside the sweep
    assert contains_all(box, arc)


def test_a_full_circle_is_bounded_by_the_circle():
    arc = ArcSegment(Vec2(3.0, -2.0), 5.0, 0.0, 2.0 * math.pi)
    box = curve_bounds(arc)
    assert_vec(box.min, Vec2(-2.0, -7.0))
    assert_vec(box.max, Vec2(8.0, 3.0))


def test_a_clockwise_arc_is_bounded_like_its_mirror():
    """The sweep's sign must not change which extremes count."""
    ccw = ArcSegment(Vec2(0.0, 0.0), 10.0, math.radians(-45.0), math.radians(90.0))
    cw = ArcSegment(Vec2(0.0, 0.0), 10.0, math.radians(45.0), math.radians(-90.0))
    assert_vec(curve_bounds(ccw).min, curve_bounds(cw).min)
    assert_vec(curve_bounds(ccw).max, curve_bounds(cw).max)


def test_an_unknown_curve_type_says_so():
    with pytest.raises(TypeError):
        curve_bounds(object())


# -- paths -----------------------------------------------------------------


def test_a_path_box_contains_every_sample_and_is_tight(demo_path):
    """Both halves of being a bound: nothing escapes it, and nothing is spare."""
    box = path_bounds(demo_path)
    for i in range(SAMPLES + 1):
        point = demo_path.sample(demo_path.length * i / SAMPLES).position
        assert box.contains(point)
    assert not contains_all(box.expanded(-EXACT), demo_path, samples=SAMPLES)


def test_a_wiggle_path_box_contains_every_sample(wiggle_path):
    box = path_bounds(wiggle_path)
    assert contains_all(box, wiggle_path, samples=SAMPLES)
