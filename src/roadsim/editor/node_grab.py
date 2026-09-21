"""Taking hold of a node - by its centre, or by one of its lane handles.

A grab is a property of the drag in progress, not of the network: it lives on
the tool that started it, never on `RoadNode`, `Selection` or a `Command`. The
command a drag eventually produces is a plain `MoveNode(node_id, position)` -
the lever has already been resolved into that position by the time anything is
recorded, so a lane grab touches undo, redo and serialization not at all.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..geometry import Vec2
from ..road.lane_handle import LaneHandle
from .context import EditorContext


@dataclass(frozen=True, slots=True)
class NodeGrab:
    node_id: int
    origin: Vec2
    """The node's position at grab time - for rewind and cancel."""
    lever: Vec2
    """Where the grabbed point sits relative to the node. `Vec2(0, 0)` for the
    plain centre handle - today's whole behaviour is this case."""
    handle: LaneHandle | None = None
    """`None` for the centre handle; set for a lane or edge handle, for the
    HUD and the preview - never read to compute the move itself."""


def grab_at(ctx: EditorContext, point: Vec2) -> NodeGrab | None:
    """What a click at `point` takes hold of. A lane handle beats the node
    centre, the way a node already beats a segment in `tools/select.py:pick`."""
    lane = ctx.snapper.nearest_lane_handle(point)
    if lane is not None:
        handle = lane.lane_handle
        return NodeGrab(
            handle.node_id,
            ctx.network.nodes[handle.node_id].position,
            handle.lever,
            handle,
        )
    node = ctx.snapper.nearest_node(point)
    if node is not None:
        return NodeGrab(
            node.node_id, ctx.network.nodes[node.node_id].position, Vec2(0.0, 0.0)
        )
    return None
