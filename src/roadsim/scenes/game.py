"""The game: one world, several modes, a real interface over the top.

The scene owns what every mode shares - the network, the context, the interface -
and the mode registry. It owns nothing about roads: that is `RoadMode`'s business,
and the scene would be identical with a traffic mode in its place.

Event order inside the scene, first consumer wins:

1. the interface, which shields the world from anything over chrome
2. these scene-level keys - save, load, undo, the mode switch: not any one mode's
   business, which is the same argument the M2 editor scene already made
3. the active mode, and through it its tools

The frame order is M2's and unchanged: handle input, rebuild dirty junctions once,
then draw.
"""

from __future__ import annotations

from pathlib import Path as FilePath

import pygame

from .. import config
from ..editor.commands import RemoveNode, RemoveSegment
from ..editor.context import EditorContext
from ..modes import DEFAULT_MODE, MODES, ModeBox
from ..render.camera import Camera
from ..render.network_renderer import NetworkRenderer
from ..road.network import RoadNetwork
from ..serialization import SchemaError, load, save
from ..ui.screen import UiScreen
from ..ui.toolbar import mode_bar
from .base import Scene
from .network_demo import build_demo_network

SAVE_PATH = FilePath("scratch/network.roadnet.json")
"""Where Ctrl+S puts it. One slot is enough until there is a file dialog."""


class GameScene(Scene):
    name = "game"

    def __init__(self, camera: Camera, network: RoadNetwork | None = None) -> None:
        super().__init__(camera)
        self.ctx = EditorContext(
            network if network is not None else build_demo_network(), camera
        )
        self.renderer = NetworkRenderer()
        self.modes = ModeBox(
            [cls() for cls in MODES],
            self.ctx,
            active=[cls.name for cls in MODES].index(DEFAULT_MODE),
        )
        self.ui = UiScreen()
        self._rebuild_ui()
        self.ctx.network.rebuild_all()

    # -- interface ---------------------------------------------------------

    def _rebuild_ui(self) -> None:
        """The mode row plus whatever the active mode contributes.

        Rebuilt on every mode change rather than shown and hidden: a widget list is
        cheap, and a stale button wired to a mode that is no longer active is the
        kind of bug that only shows up under the cursor.
        """
        switcher = mode_bar(
            self.modes.names,
            select=self._select_mode,
            active_index=lambda: self.modes.active_index,
        )
        self.ui.set_widgets([switcher, *self.modes.active.widgets(self.ctx)])
        self.ui.layout(self.camera.viewport)

    def _select_mode(self, index: int) -> None:
        if index != self.modes.active_index:
            self.modes.select(index)
            self._rebuild_ui()

    # -- input -------------------------------------------------------------

    def handle_event(self, event: pygame.event.Event) -> bool:
        if event.type == pygame.VIDEORESIZE:
            self.ui.layout((event.w, event.h))
            return False  # the app still needs to resize the camera
        if self.ui.handle_event(event):
            return True
        if event.type == pygame.KEYDOWN and self._handle_key(event):
            return True
        return self.modes.active.handle_event(event, self.ctx)

    def _handle_key(self, event: pygame.event.Event) -> bool:
        ctrl = event.mod & pygame.KMOD_CTRL
        shift = event.mod & pygame.KMOD_SHIFT

        # Shift+digit switches mode. Checked before the mode sees the event, which
        # is what keeps plain digits free for its tools.
        if shift and not ctrl and pygame.K_1 <= event.key <= pygame.K_9:
            index = event.key - pygame.K_1
            if index < len(self.modes.modes):
                self._select_mode(index)
                return True

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
        self.ctx.status = f"saved {save(self.ctx.network, SAVE_PATH)}"

    def _load(self) -> None:
        try:
            self._replace(load(SAVE_PATH), f"loaded {SAVE_PATH}")
        except (OSError, SchemaError) as exc:
            self.ctx.status = f"load failed: {exc}"

    def _replace(self, network: RoadNetwork, message: str) -> None:
        self.ctx.replace_network(network)
        self.ctx.network.rebuild_all()
        # Modes hold on to the context, so they have to be told it was swapped.
        self.modes.ctx = self.ctx
        self.modes.active.enter(self.ctx)
        self._rebuild_ui()
        self.ctx.status = message

    # -- frame -------------------------------------------------------------

    def update(self, dt: float) -> None:
        self.modes.active.update(dt, self.ctx)
        self.ctx.network.rebuild_dirty()

    def draw(self, surface: pygame.Surface) -> None:
        self.renderer.draw(surface, self.camera, self.ctx.network)
        self.modes.active.draw(surface, self.camera, self.ctx)
        self.ui.layout(self.camera.viewport)
        self.ui.draw(surface)

    @property
    def hud_origin(self) -> tuple[int, int]:
        """Below the mode row, which owns the top-left corner."""
        return (12, int(self.ui.widgets[0].rect.bottom + config.UI_GAP))

    def hud_lines(self) -> list[str]:
        network = self.ctx.network
        lines = [
            *self.modes.active.hud_lines(self.ctx),
            f"# {len(network.nodes)} nodes  {len(network.segments)} roads"
            f"  {len(network.junctions)} junctions"
            f"  |  undo depth {self.ctx.history.depth}",
            "# [Shift+1..] mode  [Tab] road type  [Ctrl+Z/Y] undo/redo"
            "  [Ctrl+S/O] save/load  [Ctrl+N/D] empty/demo  [F4] arrows",
        ]
        if self.ctx.status:
            lines.append(self.ctx.status)
        return lines
