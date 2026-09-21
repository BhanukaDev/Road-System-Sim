"""A hardcoded network that proves the road model renders before any tool exists.

This is the M2 counterpart to the `debug` scene: every shipped profile is on
screen, and every junction case the design calls out has an example here - a
four-way crossing, a T made by splitting an existing road, two profiles meeting
end to end, and dead ends. If a junction trims the wrong way or an asymmetric
profile flips its sides at the `node_b` end, you see it here immediately.

Nothing in this scene mutates the network after setup, so it stays a *scene*,
not an editor. Tools, commands and undo are the next slice of M2.
"""

from __future__ import annotations

import pygame

from .. import config
from ..geometry import Vec2
from ..road import RoadNetwork
from ..road.presets import (
    ALLEY,
    ASYMMETRIC_BOULEVARD,
    AVENUE_FOUR_LANE,
    HIGHWAY_THREE_LANE,
    ONE_WAY_TWO_LANE,
    PARKING_STREET,
    RESIDENTIAL_TWO_WAY,
)
from ..render import curves
from ..render.camera import Camera
from ..render.network_renderer import NetworkRenderer
from .base import Scene


def build_demo_network() -> RoadNetwork:
    """The scene's fixture, kept a plain function so tests can use it too."""
    net = RoadNetwork()
    origin = Vec2(0.0, 0.0)

    # A four-way crossing at the origin: a four-lane avenue crossed by a
    # residential road. Different widths on purpose - the wider road must force
    # the larger trim on the narrower one.
    net.connect(Vec2(-95.0, 0.0), origin, AVENUE_FOUR_LANE)
    net.connect(origin, Vec2(100.0, 22.0), AVENUE_FOUR_LANE, via=[Vec2(55.0, 0.0)])
    net.connect(Vec2(0.0, -80.0), origin, RESIDENTIAL_TWO_WAY)
    net.connect(origin, Vec2(-28.0, 85.0), RESIDENTIAL_TWO_WAY, via=[Vec2(0.0, 48.0)])

    # A boulevard split mid-road to make a T - which is what drawing onto an
    # existing road will do once the draw tool exists.
    boulevard = net.connect(
        Vec2(-130.0, -85.0),
        Vec2(70.0, -85.0),
        ASYMMETRIC_BOULEVARD,
        via=[Vec2(-40.0, -100.0)],
    )
    _, _, tee = net.split_segment(boulevard.id, boulevard.path.length * 0.55)
    net.connect(net.nodes[tee].position, Vec2(35.0, -165.0), ONE_WAY_TWO_LANE)

    # Two profiles meeting end to end, and a pair of dead ends to check the
    # flat caps an untrimmed end gets.
    net.connect(
        Vec2(-160.0, 60.0),
        Vec2(-70.0, 130.0),
        HIGHWAY_THREE_LANE,
        via=[Vec2(-120.0, 120.0)],
    )
    net.connect(Vec2(120.0, 95.0), Vec2(40.0, 95.0), PARKING_STREET)
    net.connect(Vec2(40.0, 95.0), Vec2(-20.0, 118.0), RESIDENTIAL_TWO_WAY)

    # A narrow alley - the other end of the width range from the avenue above.
    net.connect(Vec2(-160.0, -30.0), Vec2(-110.0, -55.0), ALLEY)

    net.rebuild_all()
    return net


class NetworkDemoScene(Scene):
    name = "network"

    def __init__(self, camera: Camera) -> None:
        super().__init__(camera)
        self.network = build_demo_network()
        self.renderer = NetworkRenderer()
        self.show_overlay = False
        self.show_centerlines = False
        self.camera.zoom = 3.0

    def handle_event(self, event: pygame.event.Event) -> bool:
        if event.type != pygame.KEYDOWN:
            return False
        if event.key == pygame.K_F2:
            self.show_overlay = not self.show_overlay
            return True
        if event.key == pygame.K_c:
            self.show_centerlines = not self.show_centerlines
            return True
        if event.key == pygame.K_a:
            self.renderer.show_arrows = not self.renderer.show_arrows
            return True
        return False

    def update(self, dt: float) -> None:
        # Nothing dirties the network here, but the call belongs in the frame
        # loop so the editor inherits the right shape: mutate, then rebuild once.
        self.network.rebuild_dirty()

    def draw(self, surface: pygame.Surface) -> None:
        self.renderer.draw(surface, self.camera, self.network)
        if self.show_centerlines:
            for segment in self.network.segments.values():
                curves.draw_path(surface, self.camera, segment.path, width=1)
        if self.show_overlay:
            self._draw_overlay(surface)

    def _draw_overlay(self, surface: pygame.Surface) -> None:
        """Nodes and control points - the authoritative state, as opposed to
        everything else on screen, which is derived from it."""
        for segment in self.network.segments.values():
            for point in segment.control_points[1:-1]:
                x, y = self.camera.to_screen(point)
                pygame.draw.rect(
                    surface, config.Color.HUD_DIM, pygame.Rect(x - 2, y - 2, 5, 5)
                )
        for node in self.network.nodes.values():
            pygame.draw.circle(
                surface,
                config.Color.NODE_MARK,
                self.camera.to_screen(node.position),
                5 if node.degree > 2 else 3,
                1,
            )

    def hud_lines(self) -> list[str]:
        junctions = sum(1 for j in self.network.junctions.values() if j.is_crossing)
        short = sum(1 for s in self.network.segments.values() if s.is_too_short)
        lines = [
            f"network  {len(self.network.nodes)} nodes"
            f"  {len(self.network.segments)} segments"
            f"  {len(self.network.junctions)} junctions ({junctions} crossings)",
            "# [F2] nodes+control points   [C] centrelines   [A] arrows",
        ]
        if short:
            lines.append(f"{short} segment(s) too short - drawn red")
        return lines
