"""Dragging a node, with the network refitting and rebuilding live.

The drag moves the node many times but leaves **one** undo step. It does that by
running `MoveNode` commands unrecorded during the drag, then putting the node
back where it started and applying a single recorded move on release. The rule
that every mutation is a `Command` (D6) holds throughout; what the drag skips is
the history, not the command.

**Grabbing by a lane is the same drag with a lever.** `NodeGrab.lever` is
`Vec2(0, 0)` for the plain centre handle - today's whole behaviour - and the
lane/edge offset for anything else (`editor/node_grab.py`). `_target` always
computes "where the held point should land" and then subtracts the lever to get
the node's own position, so this file gains no branch for the lane case at all.

**Dropped on another lane, the two roads connect (D20).** `_target` already
finds the nearest lane handle to land on; `release` remembers which one, and
if the drag was itself by a lane handle, hands off to
`editor/lane_connect.py` instead of a plain `MoveNode` - a merge plus the
datum that lines the two chosen lanes up exactly, in one undo step. Dropped
anywhere else, or grabbed by the plain centre handle, nothing about this
changes: a position move, same as always.
"""

from __future__ import annotations

import pygame

from ...geometry import Vec2
from ...road.lane_handle import LaneHandle, LaneHandleKind, node_lane_handles
from ...road.network import RoadNetwork
from ..commands import MoveNode
from ..context import EditorContext, Selection, ToolPreview
from ..handle import HandleKind, PreviewHandle
from ..lane_connect import connect_by_lane
from ..modifiers import Modifiers
from ..node_grab import NodeGrab, grab_at
from ..tool import Tool

_HANDLE_KIND = {
    LaneHandleKind.LANE: HandleKind.LANE,
    LaneHandleKind.EDGE: HandleKind.EDGE,
}


class MoveNodeTool(Tool):
    name = "move"
    hint = "drag a node, or one of its lane handles   [Shift] 15 deg   [Esc] cancel"

    def __init__(self) -> None:
        self.grab_state: NodeGrab | None = None
        self._drop_handle: LaneHandle | None = None
        """What the last `_target()` call actually landed on, if a lane
        handle - read once, by `release`, to decide whether the drag connects
        two roads or just moves one node. Never read to compute the move
        itself, which is why `_target` can keep doing that unconditionally."""

    def deactivate(self, ctx: EditorContext) -> None:
        self.cancel(ctx)

    def handle_event(self, event: pygame.event.Event, ctx: EditorContext) -> bool:
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            return self.grab(ctx, ctx.world(*event.pos))
        if event.type == pygame.MOUSEMOTION:
            ctx.cursor = ctx.world(*event.pos)
            if self.grab_state is None:
                return False
            if self.grab_state.node_id not in ctx.network.nodes:
                # Undo is a scene-level key and can land mid-drag.
                self.grab_state = None
                return False
            self.drag_to(ctx, self._target(ctx))
            return True
        if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            return self.release(ctx)
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            return self.cancel(ctx)
        return False

    # -- the drag ----------------------------------------------------------

    def grab(self, ctx: EditorContext, point: Vec2) -> bool:
        grab_state = grab_at(ctx, point)
        if grab_state is None:
            return False
        self.grab_state = grab_state
        ctx.select(Selection(node=grab_state.node_id))
        return True

    def drag_to(self, ctx: EditorContext, position: Vec2) -> None:
        # Unrecorded on purpose: the whole drag becomes one entry on release.
        MoveNode(self.grab_state.node_id, position).do(ctx.network)

    def release(self, ctx: EditorContext) -> bool:
        if self.grab_state is None:
            return False
        node_id, origin = self.grab_state.node_id, self.grab_state.origin
        grab_handle = self.grab_state.handle
        drop_handle = self._drop_handle
        self.grab_state = None
        self._drop_handle = None
        if node_id not in ctx.network.nodes:
            return True
        final = ctx.network.nodes[node_id].position
        if final.distance_to(origin) < 1e-9:
            return True
        # Rewind, then record the real change once so undo has one step to
        # reverse - a plain move, or (grabbed and dropped on a lane) a
        # connection: `editor/lane_connect.py` needs the pre-move network to
        # compute its own merge from, same as this rewind exists for.
        MoveNode(node_id, origin).do(ctx.network)
        if grab_handle is not None and drop_handle is not None:
            ctx.apply(connect_by_lane(ctx.network, grab_handle, drop_handle))
        else:
            ctx.apply(MoveNode(node_id, final))
        return True

    def cancel(self, ctx: EditorContext) -> bool:
        if self.grab_state is None:
            return False
        node_id, origin = self.grab_state.node_id, self.grab_state.origin
        self.grab_state = None
        self._drop_handle = None
        if node_id in ctx.network.nodes:
            MoveNode(node_id, origin).do(ctx.network)
        ctx.status = "move cancelled"
        return True

    def _target(self, ctx: EditorContext) -> Vec2:
        """Where the dragged node should sit, given what is currently held.

        Landing the node itself on another node through the *plain* snap
        chain would silently merge two nodes with no lane behind the choice,
        so other nodes and the node's own roads stay excluded from it - a
        lane handle is the only door to a connection (`release`, `D20`), and
        `self._drop_handle` is how this tells it which one, if any.
        """
        node_id = self.grab_state.node_id
        ignore_nodes = frozenset({node_id})
        ignore_segments = frozenset(ctx.network.nodes[node_id].segments)

        drop = ctx.snapper.nearest_lane_handle(
            ctx.cursor, ignore_nodes=ignore_nodes, ignore_segments=ignore_segments
        )
        self._drop_handle = drop.lane_handle if drop is not None else None
        if drop is None:
            mods = Modifiers.current()
            drop = ctx.snapper.snap(
                ctx.cursor,
                from_point=self.grab_state.origin,
                constrain_angle=mods.shift,
                ignore_nodes=ignore_nodes,
                ignore_segments=ignore_segments,
            )
        return drop.position - self.grab_state.lever

    # -- feedback ----------------------------------------------------------

    def preview(self, ctx: EditorContext) -> ToolPreview:
        if self.grab_state is None:
            snap = ctx.snapper.nearest_node(ctx.cursor)
            handles = _preview_handles(ctx.network, snap.node_id, None) if snap else []
            return ToolPreview(snap=snap, handles=handles)
        return ToolPreview(
            points=[self.grab_state.origin],
            rubber_band=(
                self.grab_state.origin,
                ctx.network.nodes[self.grab_state.node_id].position,
            ),
            handles=_preview_handles(
                ctx.network, self.grab_state.node_id, self.grab_state.handle
            ),
        )

    def hud_lines(self, ctx: EditorContext) -> list[str]:
        if self.grab_state is None:
            return [f"# {self.hint}"]
        node_id = self.grab_state.node_id
        moved = self.grab_state.origin.distance_to(ctx.network.nodes[node_id].position)
        line = f"moving node {node_id}   {moved:.1f} m"
        if self.grab_state.handle is not None:
            handle = self.grab_state.handle
            line += f"   by {handle.kind.value} {handle.index}"
        return [f"# {self.hint}", line]


def _preview_handles(
    network: RoadNetwork, node_id: int, active: LaneHandle | None
) -> list[PreviewHandle]:
    """Every lane and edge handle at a node, as preview data. The one matching
    `active` (the handle a drag is currently holding, if any) is marked so the
    overlay can draw it differently from the ones merely on offer."""
    return [
        PreviewHandle(handle.position, _HANDLE_KIND[handle.kind], handle == active)
        for handle in node_lane_handles(network, node_id)
    ]
