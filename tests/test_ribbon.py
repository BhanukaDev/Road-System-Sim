"""Ribbons: the strip geometry every lane, marking and texture is drawn from."""

from __future__ import annotations

import pytest

from roadsim.geometry import ArcSegment, LineSegment, Path, Vec2, build_ribbon

from .conftest import EXACT, assert_vec


def straight() -> Path:
    return Path.of(LineSegment(Vec2(0.0, 0.0), Vec2(100.0, 0.0)))


def test_edges_sit_exactly_at_the_requested_offsets(demo_path):
    ribbon = build_ribbon(demo_path, -8.0, 5.0, 0.01)
    for section in ribbon.sections:
        assert abs(section.left.distance_to(section.center) - 8.0) <= EXACT
        assert abs(section.right.distance_to(section.center) - 5.0) <= EXACT


def test_left_offset_lands_on_the_left(demo_path):
    ribbon = build_ribbon(demo_path, 3.0, -3.0, 0.05)
    for section in ribbon.sections:
        normal = demo_path.sample(section.s).normal
        assert (section.left - section.center).dot(normal) > 0.0
        assert (section.right - section.center).dot(normal) < 0.0


def test_sections_carry_increasing_arc_length(demo_path):
    """`s` is the texture V coordinate and the ruler for dashed markings."""
    ribbon = build_ribbon(demo_path, -4.0, 4.0, 0.05)
    assert ribbon.sections[0].s == 0.0
    assert abs(ribbon.sections[-1].s - demo_path.length) <= EXACT
    assert all(b.s > a.s for a, b in zip(ribbon.sections, ribbon.sections[1:]))


def test_width_and_length():
    ribbon = build_ribbon(straight(), -4.0, 3.0, 0.05)
    assert abs(ribbon.width - 7.0) <= EXACT
    assert abs(ribbon.length - 100.0) <= EXACT


def test_outline_is_a_closed_loop_down_one_edge_and_back():
    ribbon = build_ribbon(straight(), -4.0, 4.0, 0.05)
    n = len(ribbon.sections)
    assert len(ribbon.outline) == 2 * n
    assert_vec(ribbon.outline[0], ribbon.sections[0].left)
    assert_vec(ribbon.outline[-1], ribbon.sections[0].right)


def test_quads_tile_the_ribbon_without_gaps():
    ribbon = build_ribbon(straight(), -4.0, 4.0, 0.05)
    quads = ribbon.quads()
    assert len(quads) == len(ribbon.sections) - 1
    for (_, bl, br, _), (nl, _, _, nr) in zip(quads, quads[1:]):
        assert_vec(bl, nl)
        assert_vec(br, nr)


def test_a_straight_needs_only_two_sections():
    assert len(build_ribbon(straight(), -4.0, 4.0, 1e-6).sections) == 2


def test_wide_ribbons_sample_arcs_more_finely_than_narrow_ones():
    """The outer edge of a curve bulges further than the centreline does, so a
    wide road must subdivide more or its outer lane visibly facets."""
    path = Path.of(ArcSegment(Vec2(0.0, 0.0), 20.0, 0.0, 1.5))
    narrow = build_ribbon(path, -0.5, 0.5, 0.05)
    wide = build_ribbon(path, -16.0, 16.0, 0.05)
    assert len(wide.sections) > len(narrow.sections)


def test_outer_edge_stays_within_tolerance_on_a_curve():
    path = Path.of(ArcSegment(Vec2(0.0, 0.0), 20.0, 0.0, 1.5))
    tolerance = 0.05
    ribbon = build_ribbon(path, -16.0, 16.0, tolerance)
    outer_radius = 20.0 + 16.0
    worst = max(
        outer_radius - ((a.left + b.left) * 0.5).distance_to(Vec2(0.0, 0.0))
        for a, b in zip(ribbon.sections, ribbon.sections[1:])
    )
    assert worst <= tolerance + EXACT


def test_trimming_to_a_sub_range_hits_the_ends_exactly(demo_path):
    """Junction-trimmed road ends depend on this landing on the nose."""
    ribbon = build_ribbon(demo_path, -4.0, 4.0, 0.05, s0=25.0, s1=90.0)
    assert abs(ribbon.sections[0].s - 25.0) <= EXACT
    assert abs(ribbon.sections[-1].s - 90.0) <= EXACT
    assert_vec(ribbon.sections[0].center, demo_path.sample(25.0).position)
    assert_vec(ribbon.sections[-1].center, demo_path.sample(90.0).position)


def test_asymmetric_offsets_are_supported(demo_path):
    """One-sided widening must not move the centreline."""
    ribbon = build_ribbon(demo_path, 1.0, -9.0, 0.05)
    assert abs(ribbon.width - 10.0) <= EXACT
    for section in ribbon.sections:
        assert abs(section.left.distance_to(section.center) - 1.0) <= EXACT
        assert abs(section.right.distance_to(section.center) - 9.0) <= EXACT
