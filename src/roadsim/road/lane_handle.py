"""Where you can grab a node - by a lane, or by the boundary between two.

A lane handle sits *on the node itself*, unlike an `Anchor` (`road/anchor.py`),
which sits at the carriageway mouth once trims have eaten into it. Grabbing a
node by one of its lanes and dropping it on a lane of another road is an
alignment operation on the node's own position (`road/lane_handle.py` is
consumed by `editor/node_grab.py`), not a new topological relation - the same
"not a connection" reasoning D5 gives `Anchor` applies here (M4, not this
milestone).

**Deliberately built from the untrimmed end frame.** `segment.end_frame(at_a)`
is offset into the road by `trim_a`/`trim_b`, which is derived from the
junction and changes every time the network rebuilds - including mid-drag, as
the node being dragged moves. A handle whose position depended on the trim
would shift under the user's cursor while they held it. `path.sample(0.0)` /
`path.sample(path.length)` is the raw end, pinned to the node position by
`RoadNetwork.add_segment` and `set_endpoint`, and it does not move until the
drag itself moves it.
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
    node_id: int
    segment_id: int
    at_a: bool
    kind: LaneHandleKind
    index: int
    """Lane index for `LANE`; edge index 0..len(lanes) for `EDGE` - both index
    into the segment's own profile, never a lane graph id (D5)."""
    offset: float
    """Signed lateral offset in that segment's own profile, +left of A -> B."""
    normal: Vec2
    """Unit left-normal of the untrimmed end frame."""
    position: Vec2
    """`node.position + normal * offset`."""

    @property
    def lever(self) -> Vec2:
        """Where this handle sits relative to the node - what a drag preserves."""
        return self.normal * self.offset


def segment_end_handles(
    segment: RoadSegment, node_id: int, at_a: bool
) -> tuple[LaneHandle, ...]:
    """Every lane and edge handle where `segment` meets `node_id`.

    Every lane gets one, not only `carries_vehicles` ones - aligning a footway
    with a footway is as legitimate as aligning two carriageways, and a handle
    here carries no notion of what a lane is *for*.
    """
    profile = segment.profile
    frame = segment.path.sample(0.0 if at_a else segment.path.length)
    normal = frame.normal
    handles: list[LaneHandle] = []
    for k in profile.indices():
        handles.append(
            LaneHandle(
                node_id,
                segment.id,
                at_a,
                LaneHandleKind.LANE,
                k,
                profile.lane_center(k),
                normal,
                frame.position + normal * profile.lane_center(k),
            )
        )
    for i, offset in enumerate(profile.edges):
        handles.append(
            LaneHandle(
                node_id,
                segment.id,
                at_a,
                LaneHandleKind.EDGE,
                i,
                offset,
                normal,
                frame.position + normal * offset,
            )
        )
    return tuple(handles)


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
