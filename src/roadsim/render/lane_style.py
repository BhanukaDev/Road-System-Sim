"""The only place a `LaneType` becomes a colour.

`road/` deliberately does not know what a lane looks like, so that the model
stays importable without pygame and a lane type is never defined by how it is
drawn. Adding a lane type means one entry here - never a branch in the renderer.

`layer` is the paint order. Everything at the same layer is drawn together,
lowest first, so a median or a tram lane sits on top of the carriageway it is
embedded in rather than fighting it for z-order.
"""

from __future__ import annotations

from dataclasses import dataclass

from .. import config
from ..road.lane import LaneType

Color = tuple[int, int, int]


@dataclass(frozen=True, slots=True)
class LaneStyle:
    fill: Color
    edge: Color | None
    layer: int


_C = config.Color

LANE_STYLES: dict[LaneType, LaneStyle] = {
    LaneType.CAR: LaneStyle(_C.LANE_CAR, None, 0),
    LaneType.BUS: LaneStyle(_C.LANE_BUS, None, 0),
    LaneType.BIKE: LaneStyle(_C.LANE_BIKE, None, 0),
    LaneType.PARKING: LaneStyle(_C.LANE_PARKING, None, 0),
    LaneType.SHOULDER: LaneStyle(_C.LANE_SHOULDER, None, 0),
    LaneType.TRAM: LaneStyle(_C.LANE_TRAM, None, 1),
    LaneType.RAIL: LaneStyle(_C.LANE_RAIL, None, 1),
    LaneType.MEDIAN: LaneStyle(_C.LANE_MEDIAN, _C.LANE_EDGE, 2),
    LaneType.SIDEWALK: LaneStyle(_C.LANE_SIDEWALK, _C.LANE_EDGE, 2),
}

FALLBACK = LaneStyle(_C.LANE_CAR, _C.LANE_EDGE, 0)

LAYERS: tuple[int, ...] = (0, 1, 2)
"""Paint order, lowest first. Junction surfaces go down after all of them."""


def style_for(lane_type: LaneType) -> LaneStyle:
    return LANE_STYLES.get(lane_type, FALLBACK)
