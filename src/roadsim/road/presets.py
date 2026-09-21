"""The shipped cross-sections. These are the brief's cases, and they double as
the visual test set for everything downstream.

M2's design puts these in `data/profiles/*.json`; they live here as data until
`serialization/` exists to load them. The shape is the same either way - a name,
an ordered lane list and a datum - so moving them out is a loader, not a rewrite.
"""

from __future__ import annotations

from .. import config
from .lane import Direction, LaneSpec, LaneType
from .profile import RoadProfile

# Typical widths in metres, kept here so a preset reads as a cross-section
# rather than as a column of numbers.
SIDEWALK = 2.0
CAR = 3.5
ALLEY_LANE = 3.0
PARKING = 2.2
MEDIAN = 2.0
TRAM = 3.0
RAIL = 3.0
SHOULDER = 2.5

_B, _F, _2, _0 = Direction.BACKWARD, Direction.FORWARD, Direction.BOTH, Direction.NONE


def _p(name: str, *lanes: LaneSpec, datum: float = 0.0) -> RoadProfile:
    """Every preset below is authored drive-on-right, left to right of A -> B.

    Handedness is then one reversal (`config.DRIVE_ON_LEFT`): mirroring the
    lane *order* is the whole of it, because which side a travel direction
    keeps to is the only thing that changes. Flipping each lane's `direction`
    instead would look equivalent on a two-way street and be wrong on a one-way
    one - `one_way_two_lane` would start pointing B -> A, reversing a road
    against the direction it was drawn in rather than mirroring it.

    The name is untouched, so `mirrored()`'s name involution (D-2) and the
    profile-by-name keys in a save file mean the same thing either way.
    """
    ordered = tuple(reversed(lanes)) if config.DRIVE_ON_LEFT else tuple(lanes)
    return RoadProfile(name, ordered, -datum if config.DRIVE_ON_LEFT else datum)


ALLEY = _p(
    "alley",
    LaneSpec(SIDEWALK, _0, LaneType.SIDEWALK),
    LaneSpec(ALLEY_LANE, _2, LaneType.CAR, 20.0),
    LaneSpec(SIDEWALK, _0, LaneType.SIDEWALK),
)

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

PARKING_STREET = _p(
    "parking_street",
    LaneSpec(SIDEWALK, _0, LaneType.SIDEWALK),
    LaneSpec(PARKING, _0, LaneType.PARKING),
    LaneSpec(CAR, _B, LaneType.CAR, 40.0),
    LaneSpec(CAR, _F, LaneType.CAR, 40.0),
    LaneSpec(PARKING, _0, LaneType.PARKING),
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

AVENUE_FOUR_LANE = _p(
    "avenue_four_lane",
    LaneSpec(SIDEWALK, _0, LaneType.SIDEWALK),
    LaneSpec(CAR, _B, LaneType.CAR, 60.0),
    LaneSpec(CAR, _B, LaneType.CAR, 60.0),
    LaneSpec(MEDIAN, _0, LaneType.MEDIAN),
    LaneSpec(CAR, _F, LaneType.CAR, 60.0),
    LaneSpec(CAR, _F, LaneType.CAR, 60.0),
    LaneSpec(SIDEWALK, _0, LaneType.SIDEWALK),
)

HIGHWAY_THREE_LANE = _p(
    "highway_three_lane",
    LaneSpec(SHOULDER, _0, LaneType.SHOULDER),
    LaneSpec(CAR, _F, LaneType.CAR, 100.0),
    LaneSpec(CAR, _F, LaneType.CAR, 100.0),
    LaneSpec(CAR, _F, LaneType.CAR, 100.0),
    LaneSpec(SHOULDER, _0, LaneType.SHOULDER),
)

# Rail and tram are kept as real profiles for tests and future milestones, but
# are pulled out of `PROFILES` for now - no track lanes on offer until the
# texturing they need (sleepers, grooves) lands.
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
        ALLEY,
        RESIDENTIAL_TWO_WAY,
        ONE_WAY_TWO_LANE,
        PARKING_STREET,
        ASYMMETRIC_BOULEVARD,
        AVENUE_FOUR_LANE,
        HIGHWAY_THREE_LANE,
    )
}

DEFAULT_PROFILE = RESIDENTIAL_TWO_WAY


def get(name: str) -> RoadProfile:
    try:
        return PROFILES[name]
    except KeyError:
        raise KeyError(f"unknown profile {name!r}; have {sorted(PROFILES)}") from None
