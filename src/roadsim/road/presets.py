"""The shipped cross-sections. These are the brief's cases, and they double as
the visual test set for everything downstream.

M2's design puts these in `data/profiles/*.json`; they live here as data until
`serialization/` exists to load them. The shape is the same either way - a name,
an ordered lane list and a datum - so moving them out is a loader, not a rewrite.
"""

from __future__ import annotations

from .lane import Direction, LaneSpec, LaneType
from .profile import RoadProfile

# Typical widths in metres, kept here so a preset reads as a cross-section
# rather than as a column of numbers.
SIDEWALK = 2.0
CAR = 3.5
MEDIAN = 2.0
TRAM = 3.0
RAIL = 3.0
SHOULDER = 2.5

_B, _F, _2, _0 = Direction.BACKWARD, Direction.FORWARD, Direction.BOTH, Direction.NONE


def _p(name: str, *lanes: LaneSpec, datum: float = 0.0) -> RoadProfile:
    return RoadProfile(name, tuple(lanes), datum)


RESIDENTIAL_TWO_WAY = _p(
    "residential_two_way",
    LaneSpec(SIDEWALK, _0, LaneType.SIDEWALK),
    LaneSpec(CAR, _B, LaneType.CAR, 50.0),
    LaneSpec(CAR, _F, LaneType.CAR, 50.0),
    LaneSpec(SIDEWALK, _0, LaneType.SIDEWALK),
)

ONE_WAY_TWO_LANE = _p(
    "one_way_two_lane",
    LaneSpec(SIDEWALK, _0, LaneType.SIDEWALK),
    LaneSpec(CAR, _F, LaneType.CAR, 50.0),
    LaneSpec(CAR, _F, LaneType.CAR, 50.0),
    LaneSpec(SIDEWALK, _0, LaneType.SIDEWALK),
)

ASYMMETRIC_BOULEVARD = _p(
    "asymmetric_boulevard",
    LaneSpec(SIDEWALK, _0, LaneType.SIDEWALK),
    LaneSpec(CAR, _B, LaneType.CAR, 60.0),
    LaneSpec(MEDIAN, _0, LaneType.MEDIAN),
    LaneSpec(CAR, _F, LaneType.CAR, 60.0),
    LaneSpec(CAR, _F, LaneType.CAR, 60.0),
    LaneSpec(SIDEWALK, _0, LaneType.SIDEWALK),
)

TRAM_AVENUE = _p(
    "tram_avenue",
    LaneSpec(SIDEWALK, _0, LaneType.SIDEWALK),
    LaneSpec(CAR, _B, LaneType.CAR, 50.0),
    LaneSpec(TRAM, _2, LaneType.TRAM, 40.0),
    LaneSpec(CAR, _F, LaneType.CAR, 50.0),
    LaneSpec(SIDEWALK, _0, LaneType.SIDEWALK),
)

RAIL_DOUBLE = _p(
    "rail_double",
    LaneSpec(SHOULDER, _0, LaneType.SHOULDER),
    LaneSpec(RAIL, _B, LaneType.RAIL, 100.0),
    LaneSpec(RAIL, _F, LaneType.RAIL, 100.0),
    LaneSpec(SHOULDER, _0, LaneType.SHOULDER),
)

PROFILES: dict[str, RoadProfile] = {
    p.name: p
    for p in (
        RESIDENTIAL_TWO_WAY,
        ONE_WAY_TWO_LANE,
        ASYMMETRIC_BOULEVARD,
        TRAM_AVENUE,
        RAIL_DOUBLE,
    )
}

DEFAULT_PROFILE = RESIDENTIAL_TWO_WAY


def get(name: str) -> RoadProfile:
    try:
        return PROFILES[name]
    except KeyError:
        raise KeyError(f"unknown profile {name!r}; have {sorted(PROFILES)}") from None
