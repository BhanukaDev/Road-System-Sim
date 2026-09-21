"""Pavement bands around a rounded junction corner (item 15's footway continuity).

Derived from a `Junction`'s corners, like everything else at a junction (D5):
never stored, rebuilt whenever the junction is. A band exists only where both
arms meeting at a corner carry a sidewalk on the side that forms it - a corner
between two carriageways with no footway gets no band, not an empty one.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..geometry import ArcSegment, Vec2
from .junction import Junction, SegmentEnd
from .lane import LaneType
from .segment import RoadSegment


@dataclass(frozen=True)
class PavementBand:
    node_id: int
    corner_index: int
    outer_start: Vec2
    inner_start: Vec2
    curb: ArcSegment | None
    """Rounded outer edge, or `None` for a straight or hard corner."""
    inner: ArcSegment | None
    """Concentric inner edge when `curb` is rounded."""
    outer_end: Vec2
    inner_end: Vec2


def build_pavement_bands(
    junction: Junction, seg_by_key: dict[tuple[int, bool], RoadSegment]
) -> tuple[PavementBand, ...]:
    n = len(junction.ends)
    bands: list[PavementBand] = []
    for i, fillet in enumerate(junction.corners):
        a, b = junction.ends[i], junction.ends[(i + 1) % n]
        start = _sidewalk_mouth(seg_by_key, a, outgoing_left=True)
        end = _sidewalk_mouth(seg_by_key, b, outgoing_left=False)
        if start is None or end is None:
            continue
        outer_start, inner_start, width_a = start
        outer_end, inner_end, width_b = end
        if fillet is None:
            bands.append(
                PavementBand(
                    junction.node_id,
                    i,
                    outer_start,
                    inner_start,
                    None,
                    None,
                    outer_end,
                    inner_end,
                )
            )
            continue
        # The fillet runs along the *outer* edge of the footway, and its centre
        # sits out in the corner the roads leave empty - so the edge towards the
        # carriageway is the concentric arc one width *further* from that centre,
        # never the smaller one. `offset` shifts left, which is towards the
        # centre on this arc, hence the flipped sign; the radius only grows, so
        # this can never collapse.
        inner = fillet.arc.offset(-min(width_a, width_b) * fillet.arc.turn_sign)
        bands.append(
            PavementBand(
                junction.node_id,
                i,
                outer_start,
                inner_start,
                fillet.arc,
                inner,
                outer_end,
                inner_end,
            )
        )
    return tuple(bands)


def _sidewalk_mouth(
    seg_by_key: dict[tuple[int, bool], RoadSegment],
    end: SegmentEnd,
    *,
    outgoing_left: bool,
) -> tuple[Vec2, Vec2, float] | None:
    """Outer/inner sidewalk points at one trimmed mouth, viewed from the node."""
    segment = seg_by_key[(end.segment_id, end.at_a)]
    profile_left = outgoing_left == end.at_a
    lane_index = 0 if profile_left else len(segment.profile.lanes) - 1
    lane = segment.profile.lanes[lane_index]
    if lane.type is not LaneType.SIDEWALK:
        return None
    outer_index = 0 if profile_left else -1
    inner_index = 1 if profile_left else -2
    frame = segment.end_frame(end.at_a)
    outer = frame.position + frame.normal * segment.profile.edges[outer_index]
    inner = frame.position + frame.normal * segment.profile.edges[inner_index]
    return outer, inner, lane.width
