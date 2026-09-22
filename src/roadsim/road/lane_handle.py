"""Where you can take hold of a road by a lane, or by the boundary between two.

A lane handle sits on the road's *untrimmed* centreline frame at some station
`s`, offset sideways by one of the profile's own lane centres or lane edges.
Unlike an `Anchor` (`road/anchor.py`), which sits at the carriageway mouth once
trims have eaten into it, a handle is derived from stored state only, so a
junction rebuild never moves it.

Two places publish them, and they are the same object:

- **At a node** (`segment_end_handles`, `node_lane_handles`): station 0 or
  `path.length`, with `node_id` set. A road drawn onto one ends at that node
  with its profile shifted so the chosen lane lines up (`editor/lane_draw.py`,
  D21).
- **Anywhere along a road** (`segment_lane_handles`, D23): any station strictly
  inside the segment, `node_id` `None`. A road drawn onto one splits the road
  there first - the same split a plain centreline snap makes - and then joins
  the new node by the chosen lane. That is how a ramp leaves a motorway from
  its outer lane rather than from its centreline.

**Deliberately built from the untrimmed frame.** `segment.end_frame(at_a)` is
offset into the road by `trim_a`/`trim_b`, which is derived from the junction
and changes every time the network rebuilds - including mid-drag, as the node
being dragged moves. A handle whose position depended on the trim would shift
under the user's cursor while they held it. `path.sample(s)` is the raw
centreline, pinned to the control points, and it does not move until an edit
moves it.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from ..geometry import Vec2
from .network import RoadNetwork
from .segment import RoadSegment


class LaneHandleKind(Enum):
    LANE = "lane"
    """A lane's own centreline."""
    EDGE = "edge"
    """A boundary between two lanes, or one of the two kerbs."""


@dataclass(frozen=True, slots=True)
class LaneHandle:
    segment_id: int
    station: float
    """Arc length along the segment's untrimmed path where the handle's frame
    is taken: `0.0` or `path.length` for a handle at a node, anything strictly
    between for one along the road."""
    node_id: int | None
    """The node this handle sits at, or `None` for one along the road."""
    at_a: bool | None
    """Which end, for a handle at a node. Meaningless - `None` - along the road."""
    kind: LaneHandleKind
    index: int
    """Lane index for `LANE`; edge index 0..len(lanes) for `EDGE` - both index
    into the segment's own profile, never a lane graph id (D5)."""
    offset: float
    """Signed lateral offset in that segment's own profile, +left of A -> B."""
    normal: Vec2
    """Unit left-normal of the frame at `station`."""
    position: Vec2
    """`centre + normal * offset`."""

    @property
    def is_at_node(self) -> bool:
        return self.node_id is not None

    @property
    def centre(self) -> Vec2:
        """The centreline point this handle hangs off - the node for a handle
        at one, the point a split would put a node at for one along the road.
        A road drawn onto this handle ends *here*, not on the handle itself
        (`editor/lane_draw.py`, D21)."""
        return self.position - self.lever

    @property
    def lever(self) -> Vec2:
        """Where this handle sits relative to its centre - what a drag preserves."""
        return self.normal * self.offset


def segment_lane_handles(
    segment: RoadSegment,
    station: float,
    node_id: int | None = None,
    at_a: bool | None = None,
) -> tuple[LaneHandle, ...]:
    """Every lane and edge handle of `segment` at arc length `station`.

    Every lane gets one, not only `carries_vehicles` ones - aligning a footway
    with a footway is as legitimate as aligning two carriageways, and a handle
    here carries no notion of what a lane is *for*.
    """
    profile = segment.profile
    frame = segment.path.sample(station)
    normal = frame.normal
    handles: list[LaneHandle] = []
    for k in profile.indices():
        offset = profile.lane_center(k)
        handles.append(
            LaneHandle(
                segment.id,
                frame.s,
                node_id,
                at_a,
                LaneHandleKind.LANE,
                k,
                offset,
                normal,
                frame.position + normal * offset,
            )
        )
    for i, offset in enumerate(profile.edges):
        handles.append(
            LaneHandle(
                segment.id,
                frame.s,
                node_id,
                at_a,
                LaneHandleKind.EDGE,
                i,
                offset,
                normal,
                frame.position + normal * offset,
            )
        )
    return tuple(handles)


def segment_end_handles(
    segment: RoadSegment, node_id: int, at_a: bool
) -> tuple[LaneHandle, ...]:
    """Every lane and edge handle where `segment` meets `node_id`."""
    return segment_lane_handles(
        segment, 0.0 if at_a else segment.path.length, node_id, at_a
    )


def node_lane_handles(network: RoadNetwork, node_id: int) -> tuple[LaneHandle, ...]:
    """Lane and edge handles for every segment end meeting `node_id`.

    `segments_at` already counts a loop (`node_a == node_b`) twice, at its two
    distinct ends, so a loop yields two handle sets with opposing normals for
    free.
    """
    out: list[LaneHandle] = []
    for segment, at_a in network.segments_at(node_id):
        out.extend(segment_end_handles(segment, node_id, at_a))
    return tuple(out)


def handles_beside(network: RoadNetwork, handle: LaneHandle) -> tuple[LaneHandle, ...]:
    """The full set `handle` was published in - every handle at its node, or
    every handle at its station along its road - so a tool that has one can
    offer the rest of them without knowing which kind it was handed."""
    if handle.node_id is not None:
        return node_lane_handles(network, handle.node_id)
    segment = network.segments.get(handle.segment_id)
    if segment is None:
        return ()
    return segment_lane_handles(segment, handle.station)
