"""Dead-end caps: what a road looks like when it just stops.

Derived, like a junction, from the single segment end at a degree-1 node
(`RoadNode.is_dead_end`) - never stored, rebuilt whenever that node is dirty.
A cap changes nothing about the carriageway itself: no trim, no width change.
It only says what to draw past the last station (item 8).

A two-way road gets a **turning head**: a semicircular bulge spanning the full
width of the road, so the end reads as a place to turn around. A one-way road
gets a **terminal**: just a stop line, since there is nothing to turn around
for.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum

from ..geometry import ArcSegment, Vec2
from .segment import RoadSegment


class CapKind(Enum):
    TURNING_HEAD = "turning_head"
    TERMINAL = "terminal"


@dataclass(frozen=True)
class Cap:
    node_id: int
    segment_id: int
    at_a: bool
    kind: CapKind
    left: Vec2
    right: Vec2
    """Where the carriageway itself ends - a stop line runs left to right, and
    a turning head's bulge starts at `left` and ends at `right`."""
    bulge: ArcSegment | None
    """The turning head's outline, `left` to `right` through the outward side.
    `None` for a terminal - there is nothing to draw past the stop line."""


def build_cap(segment: RoadSegment, at_a: bool) -> Cap:
    """Derive the cap for one dead-end segment end.

    `at_a` follows `SegmentEnd`'s convention: True when the node sits at this
    segment's A end.
    """
    node_id = segment.node_a if at_a else segment.node_b
    frame = segment.end_frame(at_a)
    normal = frame.normal
    profile = segment.profile
    left = frame.position + normal * profile.edges[0]
    right = frame.position + normal * profile.edges[-1]

    if profile.is_oneway:
        return Cap(node_id, segment.id, at_a, CapKind.TERMINAL, left, right, None)

    radius = profile.total_width / 2.0
    center = frame.position + normal * profile.datum
    # `left` sits at `center + normal * radius`, so its own radial angle is
    # `normal`'s. A positive (CCW) sweep of pi then passes through `-tangent`
    # at its midpoint, which is "away from the network" exactly when the node
    # is at this segment's A end - the other end takes the CW sweep instead.
    turn_sign = 1.0 if at_a else -1.0
    bulge = ArcSegment(center, radius, normal.angle, turn_sign * math.pi)
    return Cap(node_id, segment.id, at_a, CapKind.TURNING_HEAD, left, right, bulge)
