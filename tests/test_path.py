"""Path: many pieces, one global arc-length parameter.

The invariants here are the ones junction trimming and vehicle movement will
lean on in later milestones.
"""

from __future__ import annotations

import math

import pytest

from roadsim.geometry import ArcSegment, LineSegment, Path, Vec2

from .conftest import EXACT, assert_vec


def straight_then_left() -> Path:
    """10m straight east, then a quarter circle of radius 10 turning left."""
    return Path.of(
        LineSegment(Vec2(-10.0, 0.0), Vec2(0.0, 0.0)),
        ArcSegment(Vec2(0.0, 10.0), 10.0, -math.pi / 2, math.pi / 2),
    )


def test_empty_path_is_refused():
    with pytest.raises(ValueError):
        Path(())


def test_length_is_the_sum_of_its_pieces(demo_path):
    assert abs(demo_path.length - sum(p.length for p in demo_path.pieces)) <= EXACT


def test_piece_starts_line_up_with_piece_lengths(demo_path):
    acc = 0.0
    for piece, start in zip(demo_path.pieces, demo_path.piece_starts):
        assert abs(start - acc) <= EXACT
        acc += piece.length


def test_sampling_crosses_piece_boundaries_continuously(demo_path):
    """No jump in position or heading at a join, or the road visibly kinks."""
    for start in demo_path.piece_starts[1:]:
        before = demo_path.sample(start - 1e-6)
        after = demo_path.sample(start + 1e-6)
        assert before.position.distance_to(after.position) <= 1e-5
        assert abs(before.tangent.cross(after.tangent)) <= 1e-5


def test_arc_length_parameterisation_is_uniform(demo_path):
    """Equal steps in s give equal distances - what dashed markings rely on."""
    step = 0.5
    chords = [
        demo_path.sample(i * step).position.distance_to(
            demo_path.sample((i + 1) * step).position
        )
        for i in range(int(demo_path.length / step) - 1)
    ]
    # Chords cut corners slightly on arcs, so allow a sagitta-sized shortfall.
    assert max(chords) <= step + EXACT
    assert min(chords) >= step - 1e-3


def test_sample_clamps_at_both_ends(demo_path):
    assert_vec(demo_path.sample(-50.0).position, demo_path.start.position)
    assert_vec(demo_path.sample(1e6).position, demo_path.end.position)


@pytest.mark.parametrize("d", [-8.0, -1.5, 3.5, 7.0])
def test_offset_is_everywhere_exactly_d_from_the_centreline(demo_path, d):
    """The headline property. Lane edges must never drift."""
    offset = demo_path.offset(d)
    for i in range(201):
        p = offset.sample(offset.length * i / 200).position
        nearest = demo_path.sample(demo_path.project(p)).position
        assert abs(p.distance_to(nearest) - abs(d)) <= EXACT


def test_offset_shortens_on_the_inside_of_a_turn():
    path = straight_then_left()
    assert path.offset(4.0).length < path.length < path.offset(-4.0).length


def test_offset_keeps_the_piece_count(demo_path):
    assert len(demo_path.offset(3.0).pieces) == len(demo_path.pieces)


def test_reversed_retraces_the_path(demo_path):
    rev = demo_path.reversed()
    assert abs(rev.length - demo_path.length) <= EXACT
    for i in range(51):
        s = demo_path.length * i / 50
        assert_vec(rev.sample(rev.length - s).position, demo_path.sample(s).position, 1e-8)


def test_trimmed_length_is_exact(demo_path):
    trimmed = demo_path.trimmed(10.0, 100.0)
    assert abs(trimmed.length - 90.0) <= EXACT
    assert_vec(trimmed.start.position, demo_path.sample(10.0).position)
    assert_vec(trimmed.end.position, demo_path.sample(100.0).position)


def test_trimmed_drops_pieces_that_fall_outside(demo_path):
    inner = demo_path.trimmed(demo_path.length - 5.0, demo_path.length)
    assert len(inner.pieces) < len(demo_path.pieces)


def test_shortened_pulls_in_both_ends(demo_path):
    """Junctions carve space out of a road exactly like this."""
    short = demo_path.shortened(10.0, 15.0)
    assert abs(short.length - (demo_path.length - 25.0)) <= EXACT
    assert_vec(short.start.position, demo_path.sample(10.0).position)


def test_trimming_to_nothing_is_refused(demo_path):
    with pytest.raises(ValueError):
        demo_path.trimmed(40.0, 40.0)


def test_project_round_trips_along_the_whole_path(demo_path):
    for i in range(201):
        s = demo_path.length * i / 200
        assert abs(demo_path.project(demo_path.sample(s).position) - s) <= 1e-8


def test_project_clamps_for_points_beyond_the_ends(demo_path):
    far_before = demo_path.start.position - demo_path.start.tangent * 500.0
    assert abs(demo_path.project(far_before)) <= EXACT


def test_flatten_spans_the_path_and_never_repeats_a_join(demo_path):
    stations = demo_path.flatten(0.05)
    assert stations[0] == 0.0
    assert abs(stations[-1] - demo_path.length) <= EXACT
    assert all(b > a for a, b in zip(stations, stations[1:]))


def test_flatten_adds_detail_as_tolerance_tightens(demo_path):
    assert len(demo_path.flatten(0.001)) > len(demo_path.flatten(0.1))


def test_flatten_error_stays_under_tolerance(demo_path):
    """What keeps curves smooth as you zoom in instead of turning into polygons."""
    tolerance = 0.02
    points = demo_path.points(tolerance)
    worst = 0.0
    for a, b in zip(points, points[1:]):
        mid = (a + b) * 0.5
        worst = max(worst, mid.distance_to(demo_path.sample(demo_path.project(mid)).position))
    assert worst <= tolerance + EXACT
