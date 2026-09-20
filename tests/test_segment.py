"""Segment geometry: the path is derived from control points, lanes from the path.

The assertion that matters is the one CLAUDE.md names: a lane edge stays exactly
its offset from the centreline. If that ever drifts, the kernel's reason for
existing has gone.
"""

from __future__ import annotations

import pytest

from roadsim.geometry import Vec2
from roadsim.road.presets import ASYMMETRIC_BOULEVARD, RESIDENTIAL_TWO_WAY
from roadsim.road.segment import RoadSegment

from .conftest import EXACT, approx, assert_vec

CORNERS = [Vec2(-50.0, 0.0), Vec2(0.0, 0.0), Vec2(40.0, 35.0), Vec2(90.0, 35.0)]


def segment(points=None, profile=RESIDENTIAL_TWO_WAY, radius=12.0) -> RoadSegment:
    return RoadSegment(1, 1, 2, list(points or CORNERS), profile, radius)


def test_path_is_fitted_from_the_control_points():
    seg = segment()
    assert_vec(seg.path.start.position, CORNERS[0])
    assert_vec(seg.path.end.position, CORNERS[-1])
    assert len(seg.path.pieces) > 1  # corners were filleted, not left as kinks


def test_moving_an_endpoint_moves_the_path_end_exactly_there():
    seg = segment()
    moved = Vec2(-60.0, 18.0)
    seg.set_endpoint(True, moved)
    assert_vec(seg.path.start.position, moved)
    assert_vec(seg.path.end.position, CORNERS[-1])


def test_lane_ribbon_edges_sit_exactly_on_the_profile_bounds():
    seg = segment(profile=ASYMMETRIC_BOULEVARD)
    for k in seg.profile.indices():
        left, right = seg.profile.lane_bounds(k)
        for section in seg.lane_ribbon(k, 0.01).sections:
            frame = seg.path.sample(section.s)
            assert_vec(section.left, frame.position + frame.normal * left)
            assert_vec(section.right, frame.position + frame.normal * right)


def test_lane_ribbon_width_is_the_lane_width_at_every_cross_section():
    seg = segment(profile=ASYMMETRIC_BOULEVARD)
    for k, lane in enumerate(seg.profile.lanes):
        for section in seg.lane_ribbon(k, 0.01).sections:
            assert approx(section.left.distance_to(section.right), lane.width)


def test_lane_ribbon_respects_the_trims():
    seg = segment()
    seg.trim_a, seg.trim_b = 6.0, 9.0
    ribbon = seg.lane_ribbon(1, 0.01)
    assert approx(ribbon.sections[0].s, 6.0)
    assert approx(ribbon.sections[-1].s, seg.path.length - 9.0)


def test_lane_centerline_is_an_exact_offset_of_the_path():
    seg = segment()
    for k in seg.profile.indices():
        offset = seg.profile.lane_center(k)
        center = seg.lane_centerline(k)
        assert_vec(
            center.start.position,
            seg.path.start.position + seg.path.start.normal * offset,
        )


def test_outgoing_direction_points_away_from_the_node_at_both_ends():
    seg = segment()
    to_b = (CORNERS[1] - CORNERS[0]).normalized()
    assert_vec(seg.outgoing_dir(True), to_b)
    assert_vec(seg.outgoing_dir(False), -seg.path.end.tangent)
    assert seg.outgoing_dir(True).dot(seg.outgoing_dir(False)) < 0.0


def test_end_frame_sits_where_the_carriageway_starts():
    seg = segment()
    seg.trim_a, seg.trim_b = 5.0, 7.0
    assert approx(seg.end_frame(True).s, 5.0)
    assert approx(seg.end_frame(False).s, seg.path.length - 7.0)


def test_is_too_short_trips_instead_of_raising():
    """Two junctions closer than their combined trim is a case the user hits
    within a minute of drawing. It must be a flag, never an exception."""
    seg = segment(points=[Vec2(0.0, 0.0), Vec2(14.0, 0.0)])
    assert not seg.is_too_short
    seg.trim_a = seg.trim_b = 7.0
    assert seg.is_too_short
    with pytest.raises(ValueError):
        _ = seg.carriageway_path  # asked for anyway, it refuses loudly


def test_carriageway_path_keeps_the_trimmed_length():
    seg = segment()
    seg.trim_a, seg.trim_b = 6.0, 9.0
    assert approx(seg.carriageway_path.length, seg.carriageway_length, 1e-6)


def test_other_node_and_is_at_a():
    seg = segment()
    assert seg.other_node(1) == 2 and seg.other_node(2) == 1
    assert seg.is_at_a(1) and not seg.is_at_a(2)
    with pytest.raises(KeyError):
        seg.other_node(99)


def test_refitting_is_stable():
    """Refitting from unchanged control points must not move the path at all."""
    seg = segment()
    before = seg.path.points(0.05)
    seg.refit()
    for a, b in zip(before, seg.path.points(0.05)):
        assert a.distance_to(b) <= EXACT
