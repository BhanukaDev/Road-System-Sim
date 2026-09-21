"""Dragging a node, with the network refitting and rebuilding live.

The drag moves the node many times but leaves **one** undo step. It does that by
running `MoveNode` commands unrecorded during the drag, then putting the node
back where it started and applying a single recorded move on release. The rule
that every mutation is a `Command` (D6) holds throughout; what the drag skips is
the history, not the command.

**One node, one handle, one question (D21).** This tool moves a node's
position; it does not connect roads and it does not offer lanes. Building a
road onto a chosen lane of another road is `tools/draw_road.py`'s job, done in
the stroke that draws it, where the lane the user picked is the reason the road
exists rather than an extra meaning read into a nudge. So the drop stays
deliberately blind to other nodes and to lane handles: landing on one changes
nothing but the position.
"""

from __future__ import annotations

import pygame

from ...geometry import Vec2
from ..commands import MoveNode
from ..context import EditorContext, Selection, ToolPreview
from ..modifiers import Modifiers
from ..node_grab import NodeGrab, grab_at
from ..tool import Tool


class MoveNodeTool(Tool):
    name = "move"
    hint = "drag a node   [Shift] 15 deg   [Esc] cancel"

    def __init__(self) -> None:
        self.grab_state: NodeGrab | None = None

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
        self.grab_state = None
        if node_id not in ctx.network.nodes:
            return True
        final = ctx.network.nodes[node_id].position
        if final.distance_to(origin) < 1e-9:
            return True
        # Rewind, then record the real change once so undo has one step to
        # reverse rather than one per mouse motion.
        MoveNode(node_id, origin).do(ctx.network)
        ctx.apply(MoveNode(node_id, final))
        return True

    def cancel(self, ctx: EditorContext) -> bool:
        if self.grab_state is None:
            return False
        node_id, origin = self.grab_state.node_id, self.grab_state.origin
        self.grab_state = None
        if node_id in ctx.network.nodes:
            MoveNode(node_id, origin).do(ctx.network)
        ctx.status = "move cancelled"
        return True

    def _target(self, ctx: EditorContext) -> Vec2:
        """Where the dragged node should sit.

        Other nodes and the node's own roads stay out of the snap chain:
        landing on another node would silently merge two nodes with nothing
        behind the choice, and snapping a node onto a road it is already an
        endpoint of would pin it to itself.
        """
        node_id = self.grab_state.node_id
        mods = Modifiers.current()
        drop = ctx.snapper.snap(
            ctx.cursor,
            from_point=self.grab_state.origin,
            constrain_angle=mods.shift,
            ignore_nodes=frozenset({node_id}),
            ignore_segments=frozenset(ctx.network.nodes[node_id].segments),
        )
        return drop.position

    # -- feedback ----------------------------------------------------------

    def preview(self, ctx: EditorContext) -> ToolPreview:
        if self.grab_state is None:
            return ToolPreview(snap=ctx.snapper.nearest_node(ctx.cursor))
        return ToolPreview(
            points=[self.grab_state.origin],
            rubber_band=(
                self.grab_state.origin,
                ctx.network.nodes[self.grab_state.node_id].position,
            ),
        )

    def hud_lines(self, ctx: EditorContext) -> list[str]:
        if self.grab_state is None:
            return [f"# {self.hint}"]
        node_id = self.grab_state.node_id
        moved = self.grab_state.origin.distance_to(ctx.network.nodes[node_id].position)
        return [f"# {self.hint}", f"moving node {node_id}   {moved:.1f} m"]
