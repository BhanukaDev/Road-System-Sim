"""The editor: draw, select, move, repaint, undo, save, load.

The scene owns the network, the context, the toolbox and the renderers, and
wires the keys that are not any one tool's business. It is deliberately thin -
anything that belongs to a tool lives in that tool, and anything that belongs
to the model lives in `road/`.

The frame order is the one the whole milestone assumes: handle input (which
queues mutations through commands), rebuild dirty junctions once, then draw.
"""

from __future__ import annotations

from pathlib import Path as FilePath

import pygame

from .. import config
from ..editor.commands import RemoveNode, RemoveSegment
from ..editor.context import EditorContext
from ..editor.overlay import EditorOverlay
from ..editor.toolbox import Toolbox
from ..render.camera import Camera
from ..render.network_renderer import NetworkRenderer
from ..road.network import RoadNetwork
from ..serialization import SchemaError, load, save
from .base import Scene
from .network_demo import build_demo_network

SAVE_PATH = FilePath("scratch/network.roadnet.json")
"""Where Ctrl+S puts it. One slot is enough until there is a file dialog."""


class EditorScene(Scene):
    name = "editor"

    def __init__(self, camera: Camera, network: RoadNetwork | None = None) -> None:
        super().__init__(camera)
        self.ctx = EditorContext(network if network is not None else RoadNetwork(), camera)
        self.toolbox = Toolbox(self.ctx)
        self.renderer = NetworkRenderer()
        self.overlay = EditorOverlay()
        self.camera.zoom = 6.0
        self.ctx.network.rebuild_all()

    # -- input -------------------------------------------------------------

    def handle_event(self, event: pygame.event.Event) -> bool:
        if event.type == pygame.KEYDOWN and self._handle_key(event):
            return True
        return self.toolbox.handle_event(event)

    def _handle_key(self, event: pygame.event.Event) -> bool:
        """Scene-level keys. Tools never see these."""
        ctrl = event.mod & pygame.KMOD_CTRL
        shift = event.mod & pygame.KMOD_SHIFT

        if ctrl and event.key == pygame.K_z:
            self.ctx.redo() if shift else self.ctx.undo()
            return True
        if ctrl and event.key == pygame.K_y:
            self.ctx.redo()
            return True
        if ctrl and event.key == pygame.K_s:
            self._save()
            return True
        if ctrl and event.key == pygame.K_o:
            self._load()
            return True
        if ctrl and event.key == pygame.K_n:
            self._replace(RoadNetwork(), "new network")
            return True
        if ctrl and event.key == pygame.K_d:
            self._replace(build_demo_network(), "demo network")
            return True
        if event.key == pygame.K_TAB:
            self.ctx.cycle_profile(-1 if shift else 1)
            return True
        if event.key in (pygame.K_DELETE, pygame.K_x):
            return self._delete_selection()
        if event.key == pygame.K_F2:
            self.overlay.show_control_points = not self.overlay.show_control_points
            return True
        if event.key == pygame.K_F3:
            self.overlay.show_nodes = not self.overlay.show_nodes
            return True
        if event.key == pygame.K_F4:
            self.renderer.show_arrows = not self.renderer.show_arrows
            return True
        return False

    def _delete_selection(self) -> bool:
        selection = self.ctx.selection
        if selection.segment is not None:
            self.ctx.apply(RemoveSegment(selection.segment))
        elif selection.node is not None:
            self.ctx.apply(RemoveNode(selection.node))
        else:
            return False
        self.ctx.clear_selection()
        return True

    # -- files -------------------------------------------------------------

    def _save(self) -> None:
        path = save(self.ctx.network, SAVE_PATH)
        self.ctx.status = f"saved {path}"

    def _load(self) -> None:
        try:
            self._replace(load(SAVE_PATH), f"loaded {SAVE_PATH}")
        except (OSError, SchemaError) as exc:
            # A bad or missing file must not take the editor down with it.
            self.ctx.status = f"load failed: {exc}"

    def _replace(self, network: RoadNetwork, message: str) -> None:
        self.ctx.replace_network(network)
        self.ctx.network.rebuild_all()
        self.toolbox.ctx = self.ctx
        self.toolbox.active.activate(self.ctx)
        self.ctx.status = message

    # -- frame -------------------------------------------------------------

    def update(self, dt: float) -> None:
        self.toolbox.update(dt)
        # Once per frame, after every command has landed - never mid-command.
        self.ctx.network.rebuild_dirty()

    def draw(self, surface: pygame.Surface) -> None:
        self.renderer.draw(surface, self.camera, self.ctx.network)
        self.overlay.draw(
            surface,
            self.camera,
            self.ctx.network,
            self.ctx.selection,
            self.toolbox.preview(),
        )

    def hud_lines(self) -> list[str]:
        network = self.ctx.network
        history = self.ctx.history
        lines = [
            *self.toolbox.hud_lines(),
            f"# {len(network.nodes)} nodes  {len(network.segments)} roads"
            f"  {len(network.junctions)} junctions"
            f"  |  undo depth {history.depth}"
            + (f"  next undo: {history.undo_label}" if history.can_undo else ""),
            "# [Tab] profile  [Ctrl+Z/Y] undo/redo  [Del] delete"
            "  [Ctrl+S/O] save/load  [Ctrl+N/D] empty/demo"
            "  [F2] control points  [F3] nodes  [F4] arrows",
        ]
        if self.ctx.status:
            lines.append(self.ctx.status)
        return lines
