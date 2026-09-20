"""Curve intersection. Exact, and the foundation under four separate features.

The central invariant, asserted everywhere below: a hit's point agrees with the
curve at `s_a` *and* with the curve at `s_b`, to machine precision. Anything less
and a crossing splits two roads at subtly different places.

The traps get their own tests, because both fail quietly rather than loudly - they
produce a plausible junction in the wrong place, which is far harder to notice
than an exception.
"""

from __future__ import annotations

import math

import pytest

from roadsim.geometry import (
    ArcSegment,
    LineSegment,
    Path,
    Vec2,
    arc_arc,
    arcs_overlap,
    curve_curve,
    fit_polyline,
    line_arc,
    line_line,
    path_intersections,
    path_self_intersections,
    path_touches,
    ray_ray,
)

from .conftest import EXACT, approx, assert_vec


def assert_hit_is_consistent(hit, a, b) -> None:
    """The one invariant: both parameterisations land on the reported point."""
    assert_vec(a.sample(hit.s_a).position, hit.point)
    assert_vec(b.sample(hit.s_b).position, hit.point)
    assert 0.0 <= hit.s_a <= a.length + EXACT
    assert 0.0 <= hit.s_b <= b.length + EXACT


# -- rays ------------------------------------------------------------------


def test_rays_cross_where_they_should():
    hit = ray_ray(Vec2(0.0, 0.0), Vec2(1.0, 0.0), Vec2(5.0, -3.0), Vec2(0.0, 1.0))
    assert_vec(hit, Vec2(5.0, 0.0))


def test_rays_reach_beyond_the_segments_that_named_them():
    """Junction trimming asks where two kerbs *would* meet, which is not the same
    question as where they do meet."""
    hit = ray_ray(Vec2(0.0, 0.0), Vec2(1.0, 0.0), Vec2(-80.0, -4.0), Vec2(0.0, 1.0))
    assert_vec(hit, Vec2(-80.0, 0.0))


def test_parallel_rays_have_no_crossing():
    assert ray_ray(Vec2(0.0, 0.0), Vec2(1.0, 0.0), Vec2(0.0, 5.0), Vec2(1.0, 0.0)) is None
    assert ray_ray(Vec2(0.0, 0.0), Vec2(1.0, 0.0), Vec2(0.0, 5.0), Vec2(-1.0, 0.0)) is None


# -- line / line -----------------------------------------------------------


def test_two_crossing_lines_report_one_hit_on_both_rulers():
    a = LineSegment(Vec2(-10.0, 0.0), Vec2(10.0, 0.0))
    b = LineSegment(Vec2(4.0, -6.0), Vec2(4.0, 6.0))
    (hit,) = line_line(a, b)
    assert_vec(hit.point, Vec2(4.0, 0.0))
    assert approx(hit.s_a, 14.0)
    assert approx(hit.s_b, 6.0)
    assert_hit_is_consistent(hit, a, b)


def test_lines_that_would_cross_past_their_ends_do_not():
    a = LineSegment(Vec2(-10.0, 0.0), Vec2(-5.0, 0.0))
    b = LineSegment(Vec2(4.0, -6.0), Vec2(4.0, 6.0))
    assert line_line(a, b) == ()


def test_lines_touching_exactly_at_an_endpoint_still_count():
    a = LineSegment(Vec2(0.0, 0.0), Vec2(10.0, 0.0))
    b = LineSegment(Vec2(10.0, 0.0), Vec2(10.0, 9.0))
    (hit,) = line_line(a, b)
    assert_vec(hit.point, Vec2(10.0, 0.0))
    assert approx(hit.s_a, a.length)
    assert approx(hit.s_b, 0.0)


def test_parallel_and_collinear_lines_report_nothing():
    a = LineSegment(Vec2(0.0, 0.0), Vec2(10.0, 0.0))
    assert line_line(a, LineSegment(Vec2(0.0, 3.0), Vec2(10.0, 3.0))) == ()
    assert line_line(a, LineSegment(Vec2(2.0, 0.0), Vec2(8.0, 0.0))) == ()


# -- line / arc ------------------------------------------------------------


def test_a_line_through_an_arc_reports_both_crossings():
    arc = ArcSegment(Vec2(0.0, 0.0), 10.0, 0.0, math.pi)  # upper half, CCW
    line = LineSegment(Vec2(-20.0, 5.0), Vec2(20.0, 5.0))
    hits = line_arc(line, arc)
    assert len(hits) == 2
    for hit in hits:
        assert_hit_is_consistent(hit, line, arc)
        assert approx(hit.point.distance_to(arc.center), arc.radius)
    assert hits[0].s_a < hits[1].s_a  # ordered along the line


def test_a_tangent_line_reports_exactly_one_hit_at_radius_distance():
    arc = ArcSegment(Vec2(0.0, 0.0), 10.0, 0.0, math.pi)
    tangent = LineSegment(Vec2(-20.0, 10.0), Vec2(20.0, 10.0))
    (hit,) = line_arc(tangent, arc)
    assert approx(hit.point.distance_to(arc.center), 10.0)
    assert_hit_is_consistent(hit, tangent, arc)


def test_a_line_missing_the_circle_reports_nothing():
    arc = ArcSegment(Vec2(0.0, 0.0), 10.0, 0.0, math.pi)
    assert line_arc(LineSegment(Vec2(-20.0, 11.0), Vec2(20.0, 11.0)), arc) == ()


def test_a_line_crossing_the_circle_outside_the_sweep_reports_nothing():
    """THE TRAP. The line crosses the full circle twice, but both crossings are on
    the half the arc does not cover. `project` would clamp them onto the arc's
    ends and report two hits at the corners - a junction in the wrong place."""
    arc = ArcSegment(Vec2(0.0, 0.0), 10.0, 0.0, math.pi)  # upper half only
    below = LineSegment(Vec2(-20.0, -5.0), Vec2(20.0, -5.0))
    assert line_arc(below, arc) == ()


def test_an_arc_whose_extension_would_cross_reports_nothing():
    """Same trap from the other side: extend the sweep and the hit appears."""
    quarter = ArcSegment(Vec2(0.0, 0.0), 10.0, 0.0, math.pi / 2.0)
    line = LineSegment(Vec2(-15.0, 5.0), Vec2(-1.0, 5.0))
    assert line_arc(line, quarter) == ()

    half = ArcSegment(Vec2(0.0, 0.0), 10.0, 0.0, math.pi)
    assert len(line_arc(line, half)) == 1


def test_line_and_arc_agree_whichever_way_round_they_are_asked():
    arc = ArcSegment(Vec2(0.0, 0.0), 10.0, 0.0, math.pi)
    line = LineSegment(Vec2(-20.0, 5.0), Vec2(20.0, 5.0))
    forward = line_arc(line, arc)
    backward = curve_curve(arc, line)
    assert len(forward) == len(backward)
    for a, b in zip(forward, sorted(backward, key=lambda h: h.s_b)):
        assert_vec(a.point, b.point)
        assert approx(a.s_a, b.s_b)
        assert approx(a.s_b, b.s_a)


# -- arc / arc -------------------------------------------------------------


def test_two_overlapping_circles_cross_twice():
    a = ArcSegment(Vec2(0.0, 0.0), 10.0, 0.0, 2.0 * math.pi)
    b = ArcSegment(Vec2(12.0, 0.0), 10.0, 0.0, 2.0 * math.pi)
    hits = arc_arc(a, b)
    assert len(hits) == 2
    for hit in hits:
        assert_hit_is_consistent(hit, a, b)
        assert approx(hit.point.distance_to(a.center), 10.0)
        assert approx(hit.point.distance_to(b.center), 10.0)


def test_externally_tangent_circles_touch_once():
    a = ArcSegment(Vec2(0.0, 0.0), 10.0, 0.0, 2.0 * math.pi)
    b = ArcSegment(Vec2(20.0, 0.0), 10.0, 0.0, 2.0 * math.pi)
    (hit,) = arc_arc(a, b)
    assert_vec(hit.point, Vec2(10.0, 0.0))


def test_separated_and_nested_circles_report_nothing():
    a = ArcSegment(Vec2(0.0, 0.0), 10.0, 0.0, 2.0 * math.pi)
    assert arc_arc(a, ArcSegment(Vec2(40.0, 0.0), 10.0, 0.0, 2.0 * math.pi)) == ()
    assert arc_arc(a, ArcSegment(Vec2(1.0, 0.0), 3.0, 0.0, 2.0 * math.pi)) == ()


def test_arcs_on_crossing_circles_but_not_crossing_sweeps_report_nothing():
    """The circles cross; these two pieces of them do not go near each other."""
    a = ArcSegment(Vec2(0.0, 0.0), 10.0, math.pi, math.pi / 4.0)
    b = ArcSegment(Vec2(12.0, 0.0), 10.0, 0.0, math.pi / 4.0)
    assert arc_arc(a, b) == ()


def test_concentric_circles_report_nothing():
    a = ArcSegment(Vec2(0.0, 0.0), 10.0, 0.0, 2.0 * math.pi)
    assert arc_arc(a, ArcSegment(Vec2(0.0, 0.0), 4.0, 0.0, 2.0 * math.pi)) == ()


def test_coincident_arcs_are_reported_as_an_overlap_not_as_a_crossing():
    """Two roads sharing a curve are not crossing at a point, they are lying on
    top of each other - a different answer, and one a tuple of hits cannot give."""
    a = ArcSegment(Vec2(0.0, 0.0), 10.0, 0.0, math.pi)
    b = ArcSegment(Vec2(0.0, 0.0), 10.0, math.pi / 2.0, math.pi / 2.0)
    assert arc_arc(a, b) == ()
    assert arcs_overlap(a, b)


def test_arcs_on_the_same_circle_that_do_not_share_any_sweep_do_not_overlap():
    a = ArcSegment(Vec2(0.0, 0.0), 10.0, 0.0, math.pi / 4.0)
    b = ArcSegment(Vec2(0.0, 0.0), 10.0, math.pi, math.pi / 4.0)
    assert not arcs_overlap(a, b)


def test_different_circles_never_overlap():
    a = ArcSegment(Vec2(0.0, 0.0), 10.0, 0.0, math.pi)
    assert not arcs_overlap(a, ArcSegment(Vec2(0.0, 0.0), 11.0, 0.0, math.pi))
    assert not arcs_overlap(a, ArcSegment(Vec2(1.0, 0.0), 10.0, 0.0, math.pi))


def test_an_unknown_curve_pairing_says_so():
    with pytest.raises(TypeError):
        curve_curve(object(), LineSegment(Vec2(0.0, 0.0), Vec2(1.0, 0.0)))


# -- paths -----------------------------------------------------------------


def cross_paths() -> tuple[Path, Path]:
    east = fit_polyline([Vec2(-60.0, 0.0), Vec2(60.0, 0.0)], 12.0)
    north = fit_polyline([Vec2(0.0, -60.0), Vec2(0.0, 60.0)], 12.0)
    return east, north


def test_two_crossing_paths_report_the_crossing_exactly():
    east, north = cross_paths()
    (hit,) = path_intersections(east, north)
    assert_vec(hit.point, Vec2(0.0, 0.0))
    assert_hit_is_consistent(hit, east, north)


def test_path_intersections_are_symmetric_under_swapping(demo_path):
    other = fit_polyline([Vec2(-20.0, -80.0), Vec2(0.0, 80.0)], 12.0)
    forward = path_intersections(demo_path, other)
    backward = path_intersections(other, demo_path)
    assert len(forward) == len(backward) >= 1
    for a, b in zip(forward, sorted(backward, key=lambda h: h.s_b)):
        assert_vec(a.point, b.point)
        assert approx(a.s_a, b.s_b)
        assert approx(a.s_b, b.s_a)


def test_hits_come_back_sorted_along_the_first_path():
    """What lets a caller split a road at each crossing in one pass."""
    zigzag = fit_polyline(
        [Vec2(-60.0, -20.0), Vec2(-20.0, 20.0), Vec2(20.0, -20.0), Vec2(60.0, 20.0)],
        8.0,
    )
    flat = fit_polyline([Vec2(-80.0, 0.0), Vec2(80.0, 0.0)], 12.0)
    hits = path_intersections(zigzag, flat)
    assert len(hits) >= 3
    assert [h.s_a for h in hits] == sorted(h.s_a for h in hits)


def test_a_crossing_exactly_on_a_join_is_reported_once():
    """A hit at a join belongs to both pieces that meet there. Reported twice, it
    becomes two splits a hair apart with a sliver of road between them."""
    bend = fit_polyline([Vec2(-40.0, 0.0), Vec2(0.0, 0.0), Vec2(40.0, 40.0)], 10.0)
    # The join between the first straight and the fillet, crossed square on.
    joint = bend.sample(bend.piece_starts[1]).position
    through = fit_polyline(
        [joint + Vec2(0.0, -30.0), joint + Vec2(0.0, 30.0)], 12.0
    )
    hits = path_intersections(bend, through)
    assert len(hits) == 1


def test_paths_that_do_not_meet_report_nothing_and_say_so_cheaply():
    east, _ = cross_paths()
    away = fit_polyline([Vec2(-60.0, 200.0), Vec2(60.0, 200.0)], 12.0)
    assert path_intersections(east, away) == ()
    assert not path_touches(east, away)


def test_path_touches_agrees_with_the_full_answer():
    east, north = cross_paths()
    assert path_touches(east, north)


# -- self-intersection -----------------------------------------------------


def test_a_road_that_never_doubles_back_does_not_self_intersect(demo_path):
    assert path_self_intersections(demo_path) == ()


def test_a_wiggle_does_not_self_intersect(wiggle_path):
    """A sine sketch bends hard but never crosses itself. A self-intersection
    test that fires here would refuse most freehand roads."""
    assert path_self_intersections(wiggle_path) == ()


def test_neighbouring_pieces_meeting_at_their_join_is_not_a_self_intersection():
    """They do meet, at the join they share. That is the path being continuous."""
    bend = fit_polyline([Vec2(-40.0, 0.0), Vec2(0.0, 0.0), Vec2(0.0, 40.0)], 10.0)
    assert len(bend.pieces) == 3
    assert path_self_intersections(bend) == ()


def test_a_figure_eight_self_intersects_exactly_once():
    """Out along one diagonal, back along the other: the legs cross at the origin
    and nowhere else, so one hit - not two, and not one per piece pair."""
    loop = fit_polyline(
        [Vec2(-40.0, -20.0), Vec2(40.0, 20.0), Vec2(40.0, -20.0), Vec2(-40.0, 20.0)],
        6.0,
    )
    hits = path_self_intersections(loop)
    assert len(hits) == 1
    hit = hits[0]
    assert_vec(hit.point, Vec2(0.0, 0.0))
    assert_vec(loop.sample(hit.s_a).position, hit.point)
    assert_vec(loop.sample(hit.s_b).position, hit.point)
    assert hit.s_a < hit.s_b


def test_a_closed_loop_meeting_only_at_its_own_corner_is_not_a_crossing():
    """Drawn back to where it started and on past it. The legs share that corner
    but never cross, and a validator that called this self-intersecting would
    refuse every roundabout."""
    closed = fit_polyline(
        [
            Vec2(-30.0, 0.0),
            Vec2(30.0, 40.0),
            Vec2(30.0, -40.0),
            Vec2(-30.0, 0.0),
            Vec2(-60.0, 0.0),
        ],
        6.0,
    )
    assert path_self_intersections(closed) == ()


def test_a_road_folded_back_on_itself_self_intersects():
    """The case a validator has to catch: drawn out and back across itself."""
    folded = fit_polyline(
        [Vec2(0.0, 0.0), Vec2(60.0, 10.0), Vec2(10.0, 30.0), Vec2(20.0, -20.0)],
        5.0,
    )
    assert path_self_intersections(folded) != ()
