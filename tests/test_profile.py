"""Cross-section maths.

The invariant under test is the one every lane, marking and junction downstream
depends on: offsets descend left to right, and they are exact.
"""

from __future__ import annotations

import pytest

from roadsim.road.lane import Direction, LaneSpec, LaneType
from roadsim.road.presets import PROFILES
from roadsim.road.profile import RoadProfile

from .conftest import EXACT, approx

CAR_F = LaneSpec(3.5, Direction.FORWARD, LaneType.CAR)
CAR_B = LaneSpec(3.5, Direction.BACKWARD, LaneType.CAR)
WALK = LaneSpec(2.0, Direction.NONE, LaneType.SIDEWALK)


def profile(*lanes: LaneSpec, datum: float = 0.0) -> RoadProfile:
    return RoadProfile("test", lanes, datum)


def test_edges_descend_left_to_right():
    edges = profile(WALK, CAR_B, CAR_F, WALK).edges
    assert list(edges) == sorted(edges, reverse=True)


def test_total_width_is_the_sum_of_lane_widths():
    p = profile(WALK, CAR_B, CAR_F, WALK)
    assert approx(p.total_width, 11.0)
    assert approx(p.edges[0] - p.edges[-1], p.total_width)


def test_lane_bounds_are_exactly_the_lane_width_apart():
    p = profile(WALK, CAR_B, CAR_F, WALK)
    for k, lane in enumerate(p.lanes):
        left, right = p.lane_bounds(k)
        assert approx(left - right, lane.width)
        assert approx(p.lane_center(k), (left + right) / 2.0)


def test_lanes_tile_the_profile_without_gaps_or_overlap():
    p = profile(WALK, CAR_B, CAR_F, WALK)
    for k in range(len(p) - 1):
        assert approx(p.lane_bounds(k)[1], p.lane_bounds(k + 1)[0], EXACT)


def test_datum_shifts_every_edge_equally_and_changes_no_width():
    plain = profile(WALK, CAR_B, CAR_F, WALK)
    shifted = profile(WALK, CAR_B, CAR_F, WALK, datum=2.5)
    assert approx(shifted.total_width, plain.total_width)
    for a, b in zip(plain.edges, shifted.edges):
        assert approx(b - a, 2.5)


def test_an_unbalanced_lane_list_still_sits_centred_on_the_centreline():
    """Asymmetry is in the *lanes*, not in where the road sits.

    Three lanes one side of the centreline and one the other does not move the
    centreline - only the datum does that (D4). This is what lets a road be
    widened on one side without dragging its junctions with it.
    """
    p = profile(WALK, CAR_B, CAR_F, CAR_F, WALK)
    assert approx(p.extent_left, p.extent_right)
    assert approx(p.extent_left + p.extent_right, p.total_width)
    assert len(p.forward_lanes) == 2 and len(p.backward_lanes) == 1


def test_the_datum_is_what_makes_a_profile_reach_further_to_one_side():
    p = profile(WALK, CAR_B, CAR_F, CAR_F, WALK, datum=-3.0)
    assert approx(p.extent_right - p.extent_left, 6.0)
    assert approx(p.extent_left + p.extent_right, p.total_width)
    assert approx(p.half_width, p.extent_right)


def test_is_oneway_is_derived_from_the_lane_list():
    assert profile(WALK, CAR_F, CAR_F, WALK).is_oneway
    assert not profile(WALK, CAR_B, CAR_F, WALK).is_oneway
    # A sidewalk is not traffic, so a road of nothing but sidewalks is neither.
    assert not profile(WALK, WALK).is_oneway


def test_both_direction_lane_counts_as_traffic_in_both_directions():
    tram = LaneSpec(3.0, Direction.BOTH, LaneType.TRAM)
    p = profile(WALK, tram, WALK)
    assert p.forward_lanes == (1,) and p.backward_lanes == (1,)
    assert not p.is_oneway


def test_mirroring_reverses_the_cross_section_exactly():
    p = profile(WALK, CAR_B, CAR_F, CAR_F, WALK)
    m = p.mirrored()
    assert approx(m.extent_left, p.extent_right)
    assert approx(m.extent_right, p.extent_left)
    assert m.forward_lanes == tuple(
        sorted(len(p) - 1 - k for k in p.backward_lanes)
    )
    assert m.mirrored().edges == p.edges


def test_a_mirror_is_named_apart_from_its_original():
    """A save file keys profiles by name, so a mirror sharing its original's name
    means one of the two silently loads as the other."""
    p = profile(WALK, CAR_B, CAR_F, CAR_F, WALK)
    assert p.mirrored().name != p.name


def test_mirroring_twice_restores_the_name_as_well_as_the_shape():
    """Which is what makes a flip-and-flip-back round trip byte-identical."""
    p = profile(WALK, CAR_B, CAR_F, CAR_F, WALK)
    there_and_back = p.mirrored().mirrored()
    assert there_and_back.name == p.name
    assert there_and_back.lanes == p.lanes
    assert approx(there_and_back.datum, p.datum)


def test_a_profile_needs_at_least_one_lane():
    with pytest.raises(ValueError):
        RoadProfile("empty", ())


def test_lane_width_must_be_positive():
    with pytest.raises(ValueError):
        LaneSpec(0.0, Direction.FORWARD, LaneType.CAR)


@pytest.mark.parametrize("name", sorted(PROFILES))
def test_every_shipped_preset_has_sane_extents(name: str):
    p = PROFILES[name]
    assert p.name == name
    assert p.total_width > 0.0
    assert approx(p.extent_left + p.extent_right, p.total_width)
    assert p.half_width == max(p.extent_left, p.extent_right)
