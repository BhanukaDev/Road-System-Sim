"""Dragging a node, with the network refitting and rebuilding live.

The drag moves the node many times but leaves **one** undo step. It does that by
running `MoveNode` commands unrecorded during the drag, then putting the node
back where it started and applying a single recorded move on release. The rule
that every mutation is a `Command` (D6) holds throughout; what the drag skips is
the history, not the command.
"""

from __future__ import annotations

import pygame

from ...geometry import Vec2
from ..commands import MoveNode
from ..context import EditorContext, Selection, ToolPreview
from ..tool import Tool


class MoveNodeTool(Tool):
    name = "move"
    hint = "drag a node   [Shift] 15 deg from where it started   [Esc] cancel"

    def __init__(self) -> None:
        self.node_id: int | None = None
        self.origin: Vec2 | None = None

    def deactivate(self, ctx: EditorContext) -> None:
        self.cancel(ctx)

    def handle_event(self, event: pygame.event.Event, ctx: EditorContext) -> bool:
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            return self.grab(ctx, ctx.world(*event.pos))
        if event.type == pygame.MOUSEMOTION:
            ctx.cursor = ctx.world(*event.pos)
            if self.node_id is None:
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
        snap = ctx.snapper.nearest_node(point)
        if snap is None:
            return False
        self.node_id = snap.node_id
        self.origin = ctx.network.nodes[self.node_id].position
        ctx.select(Selection(node=self.node_id))
        return True

    def drag_to(self, ctx: EditorContext, position: Vec2) -> None:
        # Unrecorded on purpose: the whole drag becomes one entry on release.
        MoveNode(self.node_id, position).do(ctx.network)

    def release(self, ctx: EditorContext) -> bool:
        if self.node_id is None:
            return False
        node_id, origin = self.node_id, self.origin
        final = ctx.network.nodes[node_id].position
        self.node_id, self.origin = None, None
        if final.distance_to(origin) < 1e-9:
            return True
        # Rewind, then record the move once so undo has something to reverse.
        MoveNode(node_id, origin).do(ctx.network)
        ctx.apply(MoveNode(node_id, final))
        return True

    def cancel(self, ctx: EditorContext) -> bool:
        if self.node_id is None:
            return False
        MoveNode(self.node_id, self.origin).do(ctx.network)
        self.node_id, self.origin = None, None
        ctx.status = "move cancelled"
        return True

    def _target(self, ctx: EditorContext) -> Vec2:
        """Where the dragged node should sit. Position only.

        Landing on another node would *merge* two nodes, which is a topology
        change rather than a move - so other nodes and the node's own roads are
        excluded from the snap instead of being offered as targets.
        """
        held = pygame.key.get_mods() & pygame.KMOD_SHIFT
        snap = ctx.snapper.snap(
            ctx.cursor,
            from_point=self.origin,
            constrain_angle=bool(held),
            ignore_nodes=frozenset({self.node_id}),
            ignore_segments=frozenset(ctx.network.nodes[self.node_id].segments),
        )
        return snap.position

    # -- feedback ----------------------------------------------------------

    def preview(self, ctx: EditorContext) -> ToolPreview:
        if self.node_id is None:
            return ToolPreview(snap=ctx.snapper.nearest_node(ctx.cursor))
        return ToolPreview(
            points=[self.origin],
            rubber_band=(self.origin, ctx.network.nodes[self.node_id].position),
        )

    def hud_lines(self, ctx: EditorContext) -> list[str]:
        if self.node_id is None:
            return [f"# {self.hint}"]
        moved = self.origin.distance_to(ctx.network.nodes[self.node_id].position)
        return [f"# {self.hint}", f"moving node {self.node_id}   {moved:.1f} m"]
