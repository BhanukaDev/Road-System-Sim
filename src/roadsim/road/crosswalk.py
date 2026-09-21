"""Crosswalks and stop lines at a real junction's mouths (M4, brought forward).

Only a junction with `is_crossing` (3+ arms) gets one - two arms meeting is
either a straight-through joint or a profile transition (D-notes), neither of
which is an intersection a pedestrian crosses. Geometry only, in the segment's
own arc length; `render/crosswalk_renderer.py` turns it into pixels.
"""

from __future__ import annotations

from dataclasses import dataclass

from .. import config
from .lane import LaneType
from .profile import RoadProfile
from .segment import RoadSegment


@dataclass(frozen=True, slots=True)
class CrosswalkMark:
    left: float
    right: float
    """Lateral extent, `+left` - every lane but the outer sidewalks (nothing
    to paint where a pedestrian is already standing)."""
    stripes_s0: float
    stripes_s1: float
    """Arc-length span of the zebra stripes, right at the junction mouth."""
    stop_s: float
    """Arc length of the stop line, further from the mouth than the stripes."""


def crosswalk_mark(segment: RoadSegment, at_a: bool) -> CrosswalkMark | None:
    """`None` when the profile is all sidewalk or the carriageway is too short
    to fit both the stripes and the stop line's setback - the same "flag it,
    don't crash" discipline as `is_too_short`."""
    left, right = _paved_extent(segment.profile)
    if left <= right:
        return None

    depth = config.CROSSWALK_DEPTH
    setback = config.CROSSWALK_STOP_SETBACK
    if segment.carriageway_length < depth + setback:
        return None

    if at_a:
        s0 = segment.trim_a
        stripes = (s0, s0 + depth)
        stop_s = s0 + depth + setback
    else:
        s1 = segment.path.length - segment.trim_b
        stripes = (s1 - depth, s1)
        stop_s = s1 - depth - setback
    return CrosswalkMark(left, right, *stripes, stop_s)


def _paved_extent(profile: RoadProfile) -> tuple[float, float]:
    """The profile's own edges, with any sidewalk at either end stripped off."""
    edges = profile.edges
    lanes = profile.lanes
    lo = 0
    while lo < len(lanes) and lanes[lo].type is LaneType.SIDEWALK:
        lo += 1
    hi = len(lanes) - 1
    while hi >= lo and lanes[hi].type is LaneType.SIDEWALK:
        hi -= 1
    if lo > hi:
        return 0.0, 0.0
    return edges[lo], edges[hi + 1]
