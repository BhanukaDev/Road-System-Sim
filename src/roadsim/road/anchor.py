"""Lane-aware snap anchors: where a new road naturally continues one lane of
an existing one.

An anchor is an alignment aid, not a topological relation (D5): it marks a
point and a direction along one lane's own line, at one end of one segment.
Snapping to it seeds a new road's start position and heading; the connection
it makes still resolves to an ordinary free node - lane-to-lane connectivity
is M4's, not this milestone's.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..geometry import Vec2
from .network import RoadNetwork
from .segment import RoadSegment


@dataclass(frozen=True, slots=True)
class Anchor:
    segment_id: int
    at_a: bool
    lane: int
    """Index into the segment's own profile - never a lane graph id (D5)."""
    origin: Vec2
    """Where the lane's own centreline meets this end."""
    direction: Vec2
    """Unit direction continuing that lane, away from the road."""

    def point_at(self, distance: float) -> Vec2:
        return self.origin + self.direction * distance


def end_anchors(segment: RoadSegment, at_a: bool) -> tuple[Anchor, ...]:
    """One anchor per vehicle-carrying lane at one end of `segment`.

    A sidewalk or median has nothing to continue as a road of its own, so only
    `carries_vehicles` lanes get one.
    """
    profile = segment.profile_at(at_a)
    frame = segment.end_frame(at_a)
    # `outgoing_dir` points *into* this segment (what a junction wants); an
    # anchor wants the opposite - continuing past the dead end, away from it.
    direction = frame.tangent * (-1.0 if at_a else 1.0)
    return tuple(
        Anchor(
            segment.id,
            at_a,
            k,
            frame.position + frame.normal * profile.lane_center(k),
            direction,
        )
        for k, lane in enumerate(profile.lanes)
        if lane.type.carries_vehicles
    )


def node_anchors(network: RoadNetwork, node_id: int) -> tuple[Anchor, ...]:
    """Anchors for every vehicle lane at every segment end meeting a node."""
    out: list[Anchor] = []
    for segment, at_a in network.segments_at(node_id):
        out.extend(end_anchors(segment, at_a))
    return tuple(out)
