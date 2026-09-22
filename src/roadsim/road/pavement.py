"""Pavement bands around a rounded junction corner (item 15's footway continuity).

Derived from a `Junction`'s corners, like everything else at a junction (D5):
never stored, rebuilt whenever the junction is. A band exists only where both
arms meeting at a corner carry a sidewalk on the side that forms it - a corner
between two carriageways with no footway gets no band, not an empty one.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..geometry import DegenerateOffsetError, Path, Vec2
from .junction import Junction, SegmentEnd
from .lane import LaneType
from .segment import RoadSegment


@dataclass(frozen=True)
class PavementBand:
    node_id: int
    corner_index: int
    outer_start: Vec2
    inner_start: Vec2
    curb: Path | None
    """Kerb across the corner - the junction's own blend, or `None` when there
    was no blend to build and the band closes as a straight quad."""
    inner: Path | None
    """The kerb offset by the footway's width. Offsetting arcs is exact (D1), so
    this stays a constant width from the kerb rather than drifting the way a
    resampled inner edge would."""
    outer_end: Vec2
    inner_end: Vec2


def build_pavement_bands(
    junction: Junction, seg_by_key: dict[tuple[int, bool], RoadSegment]
) -> tuple[PavementBand, ...]:
    n = len(junction.ends)
    bands: list[PavementBand] = []
    for i in range(n):
        a, b = junction.ends[i], junction.ends[(i + 1) % n]
        start = _sidewalk_mouth(seg_by_key, a, outgoing_left=True)
        end = _sidewalk_mouth(seg_by_key, b, outgoing_left=False)
        if start is None or end is None:
            continue
        outer_start, inner_start, width_a = start
        outer_end, inner_end, width_b = end
        curb = junction.blends[i] if i < len(junction.blends) else None
        inner = _inner_edge(curb, min(width_a, width_b))
        bands.append(
            PavementBand(
                junction.node_id,
                i,
                outer_start,
                inner_start,
                curb,
                inner,
                outer_end,
                inner_end,
            )
        )
    return tuple(bands)


def _inner_edge(curb: Path | None, width: float) -> Path | None:
    """The kerb pushed `width` towards the carriageway.

    The mouths are walked counter-clockwise, so the junction surface is on the
    blend's **left** the whole way round - and `offset` shifts left by this
    project's one sign convention. No `turn_sign` anywhere: which way the kerb
    happens to bend has nothing to do with which side the road is on.

    `None` when the kerb turns tighter than the footway is wide: the inner edge
    would fold through its own centre, which is `DegenerateOffsetError`. The
    band then closes straight across, the same as a corner with no blend at all -
    visibly a hard corner rather than a pavement drawn inside out.
    """
    if curb is None:
        return None
    try:
        return curb.offset(width)
    except DegenerateOffsetError:
        return None


def _sidewalk_mouth(
    seg_by_key: dict[tuple[int, bool], RoadSegment],
    end: SegmentEnd,
    *,
    outgoing_left: bool,
) -> tuple[Vec2, Vec2, float] | None:
    """Outer/inner sidewalk points at one trimmed mouth, viewed from the node."""
    segment = seg_by_key[(end.segment_id, end.at_a)]
    profile = segment.profile_at(end.at_a)
    profile_left = outgoing_left == end.at_a
    lane_index = 0 if profile_left else len(profile.lanes) - 1
    lane = profile.lanes[lane_index]
    if lane.type is not LaneType.SIDEWALK:
        return None
    outer_index = 0 if profile_left else -1
    inner_index = 1 if profile_left else -2
    frame = segment.end_frame(end.at_a)
    outer = frame.position + frame.normal * profile.edges[outer_index]
    inner = frame.position + frame.normal * profile.edges[inner_index]
    return outer, inner, lane.width
