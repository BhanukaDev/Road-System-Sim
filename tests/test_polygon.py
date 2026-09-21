"""Polygon predicates, for hovering a junction surface.

The interesting cases are the awkward ones: a concave ring, and a point sitting
exactly on the boundary. A cursor on a kerb has to land somewhere definite, or it
flickers in and out of the junction as it slides along the edge.
"""

from __future__ import annotations

from roadsim.geometry import Vec2, is_ccw, is_simple, signed_area
from roadsim.geometry.polygon import contains

from .conftest import approx

SQUARE = [Vec2(0.0, 0.0), Vec2(10.0, 0.0), Vec2(10.0, 10.0), Vec2(0.0, 10.0)]
"""Counter-clockwise with +y up (D3)."""

L_SHAPE = [
    Vec2(0.0, 0.0),
    Vec2(10.0, 0.0),
    Vec2(10.0, 4.0),
    Vec2(4.0, 4.0),
    Vec2(4.0, 10.0),
    Vec2(0.0, 10.0),
]


def test_signed_area_is_positive_counter_clockwise():
    assert approx(signed_area(SQUARE), 100.0)
    assert is_ccw(SQUARE)


def test_signed_area_flips_with_the_winding():
    assert approx(signed_area(list(reversed(SQUARE))), -100.0)
    assert not is_ccw(list(reversed(SQUARE)))


def test_a_degenerate_ring_has_no_area_and_holds_nothing():
    assert approx(signed_area([Vec2(0.0, 0.0), Vec2(1.0, 1.0)]), 0.0)
    assert not contains([Vec2(0.0, 0.0), Vec2(1.0, 1.0)], Vec2(0.5, 0.5))


def test_the_inside_of_a_square_is_inside():
    assert contains(SQUARE, Vec2(5.0, 5.0))


def test_the_outside_of_a_square_is_outside():
    for point in (Vec2(-1.0, 5.0), Vec2(11.0, 5.0), Vec2(5.0, -1.0), Vec2(5.0, 11.0)):
        assert not contains(SQUARE, point)


def test_containment_does_not_depend_on_the_winding():
    assert contains(list(reversed(SQUARE)), Vec2(5.0, 5.0))


def test_a_point_on_an_edge_counts_as_inside():
    """Left to the ray test this would answer according to rounding, so a cursor
    tracking along a kerb would flicker in and out of the junction."""
    for point in (Vec2(5.0, 0.0), Vec2(10.0, 5.0), Vec2(5.0, 10.0), Vec2(0.0, 5.0)):
        assert contains(SQUARE, point)


def test_a_corner_counts_as_inside():
    for corner in SQUARE:
        assert contains(SQUARE, corner)


def test_the_notch_of_a_concave_ring_is_outside():
    """The case a bounding box would get wrong, and the shape a junction between
    roads of different widths actually makes."""
    assert contains(L_SHAPE, Vec2(2.0, 2.0))
    assert contains(L_SHAPE, Vec2(8.0, 2.0))
    assert contains(L_SHAPE, Vec2(2.0, 8.0))
    assert not contains(L_SHAPE, Vec2(8.0, 8.0))  # the bite out of the corner


def test_a_point_level_with_two_vertices_is_not_double_counted():
    """A ray grazing a vertex is the classic way a crossing-number test flips its
    answer. Level with the notch, outside it, must read outside."""
    assert not contains(L_SHAPE, Vec2(20.0, 4.0))
    assert contains(L_SHAPE, Vec2(2.0, 4.0))


# -- self-intersection ------------------------------------------------------


def test_a_convex_ring_is_simple():
    assert is_simple([Vec2(0.0, 0.0), Vec2(4.0, 0.0), Vec2(4.0, 4.0), Vec2(0.0, 4.0)])


def test_a_concave_ring_is_still_simple():
    """Concave is not the same as broken - a junction surface is usually both
    concave and perfectly fillable."""
    assert is_simple(
        [Vec2(0.0, 0.0), Vec2(4.0, 0.0), Vec2(4.0, 4.0), Vec2(2.0, 1.0), Vec2(0.0, 4.0)]
    )


def test_a_bowtie_is_not_simple():
    """The shape a shallow junction's mouth ring used to make. Filled, it is
    bowties and holes that read as a rendering glitch."""
    assert not is_simple(
        [Vec2(0.0, 0.0), Vec2(4.0, 0.0), Vec2(0.0, 4.0), Vec2(4.0, 4.0)]
    )


def test_a_ring_that_only_grazes_itself_is_not_simple():
    """Touching at a point that is not a shared edge leaves no honest inside."""
    assert not is_simple(
        [
            Vec2(0.0, 0.0),
            Vec2(4.0, 0.0),
            Vec2(2.0, 2.0),
            Vec2(4.0, 4.0),
            Vec2(0.0, 4.0),
            Vec2(2.0, 2.0),
        ]
    )


def test_a_ring_needs_three_points_to_be_simple_at_all():
    assert not is_simple([Vec2(0.0, 0.0), Vec2(1.0, 0.0)])


def test_winding_direction_does_not_change_simplicity():
    ring = [Vec2(0.0, 0.0), Vec2(4.0, 0.0), Vec2(4.0, 4.0), Vec2(0.0, 4.0)]
    assert is_simple(ring) is is_simple(list(reversed(ring)))
