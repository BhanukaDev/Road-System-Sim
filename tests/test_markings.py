"""Lane marking derivation: the rule table in `road/markings.py`.

Tested against the shipped presets, since those double as the visual test set
for everything downstream (`presets.py`), plus small profiles for the rules a
preset does not exercise.
"""

from __future__ import annotations

from roadsim.road.lane import Direction, LaneSpec, LaneType
from roadsim.road.markings import MarkingKind, lane_markings
from roadsim.road.presets import (
    ASYMMETRIC_BOULEVARD,
    ONE_WAY_TWO_LANE,
    RAIL_DOUBLE,
    RESIDENTIAL_TWO_WAY,
    TRAM_AVENUE,
)
from roadsim.road.profile import RoadProfile

from .conftest import EXACT, approx

_B, _F, _2, _0 = Direction.BACKWARD, Direction.FORWARD, Direction.BOTH, Direction.NONE
CAR_F = LaneSpec(3.5, _F, LaneType.CAR)
CAR_B = LaneSpec(3.5, _B, LaneType.CAR)
WALK = LaneSpec(2.0, _0, LaneType.SIDEWALK)
SHOULDER = LaneSpec(2.5, _0, LaneType.SHOULDER)
PARKING = LaneSpec(2.2, _0, LaneType.PARKING)
MEDIAN = LaneSpec(2.0, _0, LaneType.MEDIAN)


def profile(*lanes: LaneSpec) -> RoadProfile:
    return RoadProfile("test", lanes)


def by_kind(profile: RoadProfile) -> dict[MarkingKind, list[float]]:
    out: dict[MarkingKind, list[float]] = {}
    for marking in lane_markings(profile):
        out.setdefault(marking.kind, []).append(marking.offset)
    return out


def test_two_way_road_gets_one_solid_centre_line_and_no_kerb_paint():
    p = RESIDENTIAL_TWO_WAY
    kinds = by_kind(p)
    assert kinds[MarkingKind.CENTER_LINE] == [approx_edge(p, 2)]
    assert MarkingKind.LANE_DIVIDER not in kinds
    assert MarkingKind.EDGE_LINE not in kinds


def test_two_same_direction_lanes_get_one_dashed_divider():
    p = ONE_WAY_TWO_LANE
    kinds = by_kind(p)
    assert kinds[MarkingKind.LANE_DIVIDER] == [approx_edge(p, 2)]
    assert MarkingKind.CENTER_LINE not in kinds


def test_a_median_is_bounded_by_two_solid_yellow_edges():
    p = ASYMMETRIC_BOULEVARD
    kinds = by_kind(p)
    assert len(kinds[MarkingKind.MEDIAN_EDGE]) == 2
    assert kinds[MarkingKind.MEDIAN_EDGE] == [approx_edge(p, 2), approx_edge(p, 3)]
    # The two forward lanes still get their own dashed divider.
    assert kinds[MarkingKind.LANE_DIVIDER] == [approx_edge(p, 4)]


def test_a_track_lane_carries_no_markings_at_all():
    kinds = by_kind(TRAM_AVENUE)
    assert kinds == {}
    kinds = by_kind(RAIL_DOUBLE)
    assert kinds == {}


def test_shoulder_and_parking_get_a_solid_white_edge_line():
    p = profile(SHOULDER, CAR_F, CAR_F, PARKING)
    kinds = by_kind(p)
    assert kinds[MarkingKind.EDGE_LINE] == [approx_edge(p, 1), approx_edge(p, 3)]
    assert kinds[MarkingKind.LANE_DIVIDER] == [approx_edge(p, 2)]


def test_outer_vehicle_edges_get_a_fog_line_even_with_no_neighbour():
    p = profile(CAR_B, CAR_F)
    kinds = by_kind(p)
    assert set(kinds[MarkingKind.EDGE_LINE]) == {p.edges[0], p.edges[-1]}


def test_a_sidewalk_boundary_carries_no_marking():
    p = profile(WALK, CAR_F, WALK)
    kinds = by_kind(p)
    assert MarkingKind.EDGE_LINE not in kinds


def test_markings_are_derived_not_stored_and_cache_by_identity():
    p = RESIDENTIAL_TWO_WAY
    assert lane_markings(p) is lane_markings(p)


def approx_edge(profile: RoadProfile, index: int) -> float:
    return profile.edges[index]
