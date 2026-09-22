"""Taking hold of a node.

A grab is a property of the drag in progress, not of the network: it lives on
the tool that started it, never on `RoadNode`, `Selection` or a `Command`. The
command a drag eventually produces is a plain `MoveNode(node_id, position)`,
so a grab touches undo, redo and serialization not at all.

**A node is grabbed by its centre and nothing else (D21).** Lane handles were
briefly offered here too, so that dropping one lane on another connected two
roads; the alignment question moved to `tools/draw_road.py`, where a road is
*built* across a chosen part of another road in the same stroke that draws it
(D25). Moving a node is about where it sits, so the move tool asks one
question and gets one answer - and a node carrying six or eight rings while
you only wanted to nudge it said otherwise.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..geometry import Vec2
from .context import EditorContext


@dataclass(frozen=True, slots=True)
class NodeGrab:
    node_id: int
    origin: Vec2
    """The node's position at grab time - for rewind and cancel."""


def grab_at(ctx: EditorContext, point: Vec2) -> NodeGrab | None:
    """What a click at `point` takes hold of."""
    node = ctx.snapper.nearest_node(point)
    if node is None:
        return None
    return NodeGrab(node.node_id, ctx.network.nodes[node.node_id].position)
