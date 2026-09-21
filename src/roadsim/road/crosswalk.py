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
    stop_left: float
    stop_right: float
    """Lateral extent of the *stop line*, which is not the crosswalk's.

    A zebra spans the whole carriageway, because a pedestrian crosses all of
    it. A stop line holds back only the traffic arriving at this mouth, so it
    covers the approach half alone - the lanes travelling towards this end and
    no others. Paint it full width and both ends of a segment get an identical
    band, which reads as two stop lines on the same side of the road instead of
    one on each approach.

    `stop_left <= stop_right` means there is no stop line here at all - the
    same empty-span convention `_paved_extent` uses. That is the right answer,
    not a failure: a one-way arm *leaving* a junction has nothing to stop.
    """

    @property
    def has_stop_line(self) -> bool:
        return self.stop_left > self.stop_right


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
    stop_left, stop_right = _approach_extent(segment.profile, at_a)
    return CrosswalkMark(left, right, *stripes, stop_s, stop_left, stop_right)


def approach_lanes(profile: RoadProfile, at_a: bool) -> tuple[int, ...]:
    """The lanes arriving at this end - the ones a stop line holds back.

    Direction is relative to the segment's own A -> B (`lane.py`), so traffic
    reaching end A is the `BACKWARD` group and traffic reaching end B is the
    `FORWARD` one. Handedness does not come into it: which lanes approach is a
    question about travel direction, not about which side of the road they
    keep to.
    """
    return profile.backward_lanes if at_a else profile.forward_lanes


def _approach_extent(profile: RoadProfile, at_a: bool) -> tuple[float, float]:
    """Lateral span of the approach half, `+left`, empty when nothing arrives.

    Taken as the outer bounds of the approaching group rather than lane by
    lane, so a stop line stays one unbroken band across the lanes it holds -
    including anything sitting between them, which is what a real one does.
    """
    lanes = approach_lanes(profile, at_a)
    if not lanes:
        return 0.0, 0.0
    edges = profile.edges
    return edges[min(lanes)], edges[max(lanes) + 1]


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
