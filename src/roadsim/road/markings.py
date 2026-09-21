"""Lane markings, derived from adjacent `LaneSpec` pairs (M4, brought forward).

No colours live here - same split as `lane.py` / `render/lane_style.py`: `road/`
decides *what* line goes where and whether it is broken, `render/` decides what
it looks like, so `road/` stays importable without pygame.

A marking is pure profile data - a lateral offset and a kind, nothing about arc
length. Trimming a marking to a segment's carriageway (`trim_a` .. `length -
trim_b`) is the renderer's job, using the exact same span the segment's lanes
and direction arrows already stop at. That span is what a junction has already
cut back to for *any* meeting angle - square or shallow - so a marking simply
stops where the road does and never needs a junction-angle case of its own.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from functools import lru_cache

from .lane import Direction, LaneSpec, LaneType
from .profile import RoadProfile


class MarkingKind(Enum):
    LANE_DIVIDER = "lane_divider"
    """Between two lanes carrying traffic the same way - crossable, so dashed."""
    CENTER_LINE = "center_line"
    """Between opposing traffic with no median between - solid, never crossed."""
    MEDIAN_EDGE = "median_edge"
    """Where a vehicle lane meets a median - solid, same reason as the centre."""
    EDGE_LINE = "edge_line"
    """The road's outer edge, or against a shoulder/parking lane - solid, white."""

    @property
    def is_dashed(self) -> bool:
        return self is MarkingKind.LANE_DIVIDER


@dataclass(frozen=True, slots=True)
class LaneMarking:
    offset: float
    """Lateral offset from the centreline, `+left`, same convention as `edges`."""
    kind: MarkingKind


@lru_cache(maxsize=None)
def lane_markings(profile: RoadProfile) -> tuple[LaneMarking, ...]:
    """Every marking this profile carries, left to right.

    Cached per profile: a profile is immutable and shared across every segment
    that uses it, so this is derived once per shape rather than once per frame.
    """
    edges = profile.edges
    lanes = profile.lanes
    out: list[LaneMarking] = []

    if lanes[0].type.carries_vehicles:
        out.append(LaneMarking(edges[0], MarkingKind.EDGE_LINE))
    if lanes[-1].type.carries_vehicles:
        out.append(LaneMarking(edges[-1], MarkingKind.EDGE_LINE))

    for i in range(1, len(lanes)):
        kind = _boundary_kind(lanes[i - 1], lanes[i])
        if kind is not None:
            out.append(LaneMarking(edges[i], kind))
    return tuple(out)


def _boundary_kind(left: LaneSpec, right: LaneSpec) -> MarkingKind | None:
    """The one rule table. A new lane type needs an entry here, never a branch
    anywhere a marking is drawn."""
    if left.type.is_track or right.type.is_track:
        return None  # a rail/tram lane carries sleepers or grooves, not paint

    left_v, right_v = left.type.carries_vehicles, right.type.carries_vehicles

    if left_v and right_v:
        return (
            MarkingKind.CENTER_LINE
            if _opposing(left.direction, right.direction)
            else MarkingKind.LANE_DIVIDER
        )
    if not (left_v or right_v):
        return None  # e.g. a sidewalk against a shoulder - nothing to paint

    # Exactly one side carries traffic; a kerb needs no paint, but a median or a
    # shoulder/parking lane is a real edge of the carriageway.
    if LaneType.MEDIAN in (left.type, right.type):
        return MarkingKind.MEDIAN_EDGE
    if LaneType.SHOULDER in (left.type, right.type) or LaneType.PARKING in (
        left.type,
        right.type,
    ):
        return MarkingKind.EDGE_LINE
    return None


def _opposing(a: Direction, b: Direction) -> bool:
    return {a, b} == {Direction.FORWARD, Direction.BACKWARD}
