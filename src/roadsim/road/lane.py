"""Lane types, directions and the single-lane cross-section spec.

A lane is *only* a width, a direction and a type. Everything a road can be -
two-way, one-way, asymmetric, tram-in-road, plain rail - comes from the ordering
of these in a `RoadProfile` (D4), never from flags.

No colors live here. The LaneType-to-color mapping is a rendering concern and
belongs in `render/lane_style.py`; `road/` stays importable without pygame.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class LaneType(Enum):
    CAR = "car"
    BUS = "bus"
    BIKE = "bike"
    TRAM = "tram"
    RAIL = "rail"
    PARKING = "parking"
    SIDEWALK = "sidewalk"
    MEDIAN = "median"
    SHOULDER = "shoulder"

    @property
    def carries_vehicles(self) -> bool:
        """Something drives along it. M4 asks this when it derives the lane graph."""
        return self in _VEHICLE_LANES

    @property
    def carries_pedestrians(self) -> bool:
        return self in _PEDESTRIAN_LANES

    @property
    def is_track(self) -> bool:
        """Runs on rails, so it gets sleepers or grooves rather than markings (M3)."""
        return self in _TRACK_LANES


_VEHICLE_LANES = frozenset(
    {LaneType.CAR, LaneType.BUS, LaneType.BIKE, LaneType.TRAM, LaneType.RAIL}
)
_PEDESTRIAN_LANES = frozenset({LaneType.SIDEWALK})
_TRACK_LANES = frozenset({LaneType.TRAM, LaneType.RAIL})


class Direction(Enum):
    """Travel direction relative to the segment's A -> B direction."""

    FORWARD = "forward"
    BACKWARD = "backward"
    BOTH = "both"
    NONE = "none"

    @property
    def is_traffic(self) -> bool:
        return self is not Direction.NONE

    def flipped(self) -> Direction:
        if self is Direction.FORWARD:
            return Direction.BACKWARD
        if self is Direction.BACKWARD:
            return Direction.FORWARD
        return self


@dataclass(frozen=True, slots=True)
class LaneSpec:
    width: float
    direction: Direction
    type: LaneType
    speed_limit: float | None = None

    def __post_init__(self) -> None:
        if self.width <= 0.0:
            raise ValueError(f"lane width must be positive, got {self.width}")
