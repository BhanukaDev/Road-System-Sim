"""Fitting corner points into a tangent-arc-tangent path.

The properties that matter: the result is tangent-continuous (no kinks), fillets
never overlap however short the straights get, and identical corners produce
identical radii regardless of which end the clamping starts from.
"""

from __future__ import annotations

import math

import pytest

from roadsim.geometry import ArcSegment, LineSegment, Vec2, fit_freehand, fit_polyline, simplify

from .conftest import EXACT, assert_vec


def arcs(path):
    return [p for p in path.pieces if isinstance(p, ArcSegment)]


def test_two_points_make_a_single_straight():
    path = fit_polyline([Vec2(0.0, 0.0), Vec2(10.0, 0.0)], 12.0)
    assert len(path.pieces) == 1
    assert isinstance(path.pieces[0], LineSegment)
    assert abs(path.length - 10.0) <= EXACT


def test_fewer_than_two_distinct_points_is_refused():
    with pytest.raises(ValueError):
        fit_polyline([Vec2(1.0, 1.0)], 12.0)
    with pytest.raises(ValueError):
        fit_polyline([Vec2(1.0, 1.0), Vec2(1.0, 1.0)], 12.0)


def test_duplicate_points_are_dropped():
    path = fit_polyline(
        [Vec2(0.0, 0.0), Vec2(0.0, 0.0), Vec2(50.0, 0.0), Vec2(50.0, 50.0)], 10.0
    )
    assert len(arcs(path)) == 1


def test_collinear_points_stay_straight():
    """No arc should be invented where the road does not actually turn."""
    path = fit_polyline([Vec2(0.0, 0.0), Vec2(30.0, 0.0), Vec2(90.0, 0.0)], 12.0)
    assert arcs(path) == []
    assert abs(path.length - 90.0) <= EXACT


def test_endpoints_are_preserved():
    start, end = Vec2(-90.0, -30.0), Vec2(95.0, -25.0)
    path = fit_polyline([start, Vec2(-10.0, 20.0), Vec2(45.0, -20.0), end], 12.0)
    assert_vec(path.start.position, start)
    assert_vec(path.end.position, end)


def test_result_is_tangent_continuous(demo_path):
    """A tangency slip here shows up as a visible kink in the road."""
    for a, b in zip(demo_path.pieces, demo_path.pieces[1:]):
        assert a.end.position.distance_to(b.start.position) <= 1e-9
        assert abs(a.end.tangent.cross(b.start.tangent)) <= 1e-9
        assert a.end.tangent.dot(b.start.tangent) > 0.0


def test_pieces_alternate_line_and_arc(demo_path):
    kinds = [type(p).__name__ for p in demo_path.pieces]
    assert all(a != b for a, b in zip(kinds, kinds[1:]))


def test_a_gentle_corner_gets_the_requested_radius():
    """Long straights leave room, so no clamping should kick in."""
    path = fit_polyline([Vec2(0.0, 0.0), Vec2(200.0, 0.0), Vec2(200.0, 200.0)], 12.0)
    assert abs(arcs(path)[0].radius - 12.0) <= EXACT


def test_turn_direction_matches_the_corner():
    left = fit_polyline([Vec2(0.0, 0.0), Vec2(100.0, 0.0), Vec2(100.0, 100.0)], 12.0)
    right = fit_polyline([Vec2(0.0, 0.0), Vec2(100.0, 0.0), Vec2(100.0, -100.0)], 12.0)
    assert arcs(left)[0].sweep > 0.0
    assert arcs(right)[0].sweep < 0.0


def test_sweep_equals_the_deflection_angle():
    path = fit_polyline([Vec2(0.0, 0.0), Vec2(100.0, 0.0), Vec2(100.0, 100.0)], 12.0)
    assert abs(abs(arcs(path)[0].sweep) - math.pi / 2) <= EXACT


def test_short_straights_shrink_the_radius_instead_of_overlapping():
    """A 12m fillet cannot fit two 90-degree corners 5m apart, so it gives way."""
    path = fit_polyline(
        [Vec2(0.0, 0.0), Vec2(5.0, 0.0), Vec2(5.0, 5.0), Vec2(10.0, 5.0)], 12.0
    )
    fitted = arcs(path)
    assert len(fitted) == 2
    assert all(a.radius < 12.0 for a in fitted)


def test_identical_corners_get_identical_radii():
    """Order-independence: clamping from either end must give the same road."""
    path = fit_polyline(
        [Vec2(0.0, 0.0), Vec2(5.0, 0.0), Vec2(5.0, 5.0), Vec2(10.0, 5.0)], 12.0
    )
    a, b = arcs(path)
    assert abs(a.radius - b.radius) <= EXACT
    assert abs(a.radius - 2.5) <= EXACT


def test_fillets_never_eat_more_than_their_straight():
    """Overlapping fillets would produce a self-crossing centreline."""
    pts = [Vec2(0.0, 0.0), Vec2(6.0, 0.0), Vec2(9.0, 7.0), Vec2(16.0, 4.0), Vec2(20.0, 12.0)]
    path = fit_polyline(pts, 30.0)
    for a, b in zip(path.pieces, path.pieces[1:]):
        assert_vec(a.end.position, b.start.position, 1e-9)
    assert path.length > 0.0


def test_a_reversal_is_left_as_a_kink_not_a_bad_arc():
    """180 degrees cannot be filleted; better a hard corner than a broken arc."""
    path = fit_polyline([Vec2(0.0, 0.0), Vec2(50.0, 0.0), Vec2(0.0, 0.0001)], 12.0)
    assert arcs(path) == []


def test_every_fitted_path_offsets_without_collapsing(wiggle_path):
    """A tight fillet plus a wide lane is where DegenerateOffsetError lurks."""
    for d in (-8.0, -4.5, 1.5, 5.0):
        offset = wiggle_path.offset(d)
        assert offset.length > 0.0


# -- stroke simplification -------------------------------------------------


def test_simplify_keeps_the_endpoints():
    pts = [Vec2(float(i), math.sin(i / 5.0)) for i in range(50)]
    out = simplify(pts, 0.5)
    assert_vec(out[0], pts[0])
    assert_vec(out[-1], pts[-1])


def test_simplify_drops_points_on_a_straight():
    pts = [Vec2(float(i), 0.0) for i in range(50)]
    assert len(simplify(pts, 0.1)) == 2


def test_simplify_keeps_more_detail_as_tolerance_tightens():
    pts = [Vec2(float(i), 25.0 * math.sin(i / 8.0)) for i in range(120)]
    assert len(simplify(pts, 0.1)) > len(simplify(pts, 5.0)) >= 2


def test_simplify_stays_within_tolerance_of_the_original():
    pts = [Vec2(float(i), 25.0 * math.sin(i / 8.0)) for i in range(120)]
    kept = simplify(pts, 1.0)
    for p in pts:
        best = min(
            p.distance_to(LineSegment(a, b).sample(LineSegment(a, b).project(p)).position)
            for a, b in zip(kept, kept[1:])
        )
        assert best <= 1.0 + 1e-6


def test_freehand_stroke_becomes_a_road_shaped_path():
    """The organic-drawing bridge: a squiggle in, alternating lines and arcs out."""
    stroke = [Vec2(float(t), 25.0 * math.sin(t / 18.0)) for t in range(0, 170, 3)]
    path = fit_freehand(stroke, radius=12.0, tolerance=2.0)
    assert len(arcs(path)) >= 4
    for a, b in zip(path.pieces, path.pieces[1:]):
        assert abs(a.end.tangent.cross(b.start.tangent)) <= 1e-9
