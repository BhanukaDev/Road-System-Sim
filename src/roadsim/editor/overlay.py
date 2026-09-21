"""Everything the editor draws on top of the network.

Tools produce a `ToolPreview` as geometry; this file is the only place in
`editor/` that turns anything into pixels. It reads the model and the preview
and mutates neither - the same read-only contract the renderers in `render/`
work under (D8).
"""

from __future__ import annotations

import pygame

from .. import config
from ..geometry import build_ribbon
from ..render.camera import Camera
from ..render.curves import to_screen_points
from ..render.lane_style import LAYERS, style_for
from ..road.network import RoadNetwork
from .context import Selection, ToolPreview
from .handle import HandleKind, PreviewHandle
from .snapping import Snap, SnapKind

SNAP_COLORS = {
    SnapKind.NODE: config.Color.SNAP_NODE,
    SnapKind.ANCHOR: config.Color.SNAP_ANCHOR,
    SnapKind.SEGMENT: config.Color.SNAP_SEGMENT,
    SnapKind.ANGLE: config.Color.SNAP_ANGLE,
    SnapKind.GRID: config.Color.SNAP_GRID,
    SnapKind.LANE: config.Color.SNAP_LANE,
}

HANDLE_STYLES: dict[HandleKind, tuple[tuple[int, int, int], int, int]] = {
    HandleKind.LANE: (config.Color.HANDLE_LANE, 4, 1),
    HandleKind.EDGE: (config.Color.HANDLE_EDGE, 3, 1),
    HandleKind.CONTROL: (config.Color.HANDLE_CONTROL, 5, 0),
    HandleKind.ARC_MID: (config.Color.HANDLE_DERIVED, 4, 1),
    HandleKind.ARC_END: (config.Color.HANDLE_DERIVED, 3, 1),
    HandleKind.STRAIGHT_MID: (config.Color.HANDLE_DERIVED, 3, 1),
}
"""Colour, screen radius and outline width per handle kind. A registry rather
than a branch: a new kind is one line here and it appears on screen."""


class EditorOverlay:
    def __init__(self, show_nodes: bool = True) -> None:
        self.show_nodes = show_nodes
        self.show_control_points = False

    def draw(
        self,
        surface: pygame.Surface,
        camera: Camera,
        network: RoadNetwork,
        selection: Selection,
        preview: ToolPreview,
    ) -> None:
        if self.show_control_points:
            self._draw_control_points(surface, camera, network)
        self._draw_selection(surface, camera, network, selection)
        if self.show_nodes:
            self._draw_nodes(surface, camera, network, selection)
        self._draw_preview(surface, camera, preview)

    # -- the model ---------------------------------------------------------

    def _draw_nodes(
        self,
        surface: pygame.Surface,
        camera: Camera,
        network: RoadNetwork,
        selection: Selection,
    ) -> None:
        """Nodes are authoritative state, so they are always worth seeing.

        A junction node is drawn larger than a plain joint - the difference is
        the thing most worth reading at a glance.
        """
        for node in network.nodes.values():
            selected = node.id == selection.node
            color = config.Color.NODE_SELECTED if selected else config.Color.NODE_MARK
            radius = 6 if node.degree > 2 else 4
            pygame.draw.circle(
                surface,
                color,
                camera.to_screen(node.position),
                radius,
                0 if selected else 2,
            )

    def _draw_control_points(
        self, surface: pygame.Surface, camera: Camera, network: RoadNetwork
    ) -> None:
        for segment in network.segments.values():
            for point in segment.control_points[1:-1]:
                x, y = camera.to_screen(point)
                pygame.draw.rect(
                    surface, config.Color.HUD_DIM, pygame.Rect(x - 2, y - 2, 5, 5)
                )

    def _draw_selection(
        self,
        surface: pygame.Surface,
        camera: Camera,
        network: RoadNetwork,
        selection: Selection,
    ) -> None:
        if selection.segment is None or selection.segment not in network.segments:
            return
        segment = network.segments[selection.segment]
        points = to_screen_points(camera, segment.path.points(camera.world_tolerance))
        if len(points) >= 2:
            pygame.draw.lines(surface, config.Color.SELECTION, False, points, 3)

    # -- the tool ----------------------------------------------------------

    def _draw_preview(
        self, surface: pygame.Surface, camera: Camera, preview: ToolPreview
    ) -> None:
        color = config.Color.SEGMENT_ERROR if preview.invalid else config.Color.PREVIEW

        for guide in preview.guides:
            _dashed_line(
                surface,
                config.Color.GUIDE,
                camera.to_screen(guide.anchor),
                camera.to_screen(guide.point),
            )

        if preview.profile is not None:
            for layer in LAYERS:
                for path in preview.paths:
                    self._draw_preview_lanes(
                        surface, camera, path, preview.profile, layer, preview.invalid
                    )

        for path in preview.paths:
            points = to_screen_points(camera, path.points(camera.world_tolerance))
            if len(points) >= 2:
                pygame.draw.lines(surface, color, False, points, 2)

        if preview.rubber_band is not None:
            a, b = preview.rubber_band
            pygame.draw.line(
                surface,
                config.Color.PREVIEW_DIM,
                camera.to_screen(a),
                camera.to_screen(b),
                1,
            )

        for point in preview.points:
            pygame.draw.circle(surface, color, camera.to_screen(point), 4, 1)

        if preview.measurement is not None and preview.paths:
            path = preview.paths[-1]
            anchor = path.sample(path.length / 2.0).position
            x, y = camera.to_screen(anchor)
            label = pygame.font.SysFont("consolas,menlo,monospace", 12).render(
                f"{preview.measurement:.1f} m",
                True,
                config.Color.HUD_TEXT,
            )
            surface.blit(label, (x + 8, y - 8))

        for readout in preview.angles:
            x, y = camera.to_screen(readout.position)
            label = pygame.font.SysFont("consolas,menlo,monospace", 12).render(
                f"{readout.degrees:.0f} deg",
                True,
                config.Color.HUD_TEXT,
            )
            surface.blit(label, (x + 8, y + 8))

        if preview.invalid and preview.reason and preview.points:
            x, y = camera.to_screen(preview.points[-1])
            label = pygame.font.SysFont("consolas,menlo,monospace", 12).render(
                preview.reason, True, config.Color.SEGMENT_ERROR
            )
            surface.blit(label, (x + 8, y - 20))

        self._draw_handles(surface, camera, preview.handles)

        if preview.snap is not None:
            self._draw_snap(surface, camera, preview.snap)

    def _draw_handles(
        self,
        surface: pygame.Surface,
        camera: Camera,
        handles: list[PreviewHandle],
    ) -> None:
        for handle in handles:
            color, radius, width = HANDLE_STYLES[handle.kind]
            if handle.active:
                color, width = config.Color.HANDLE_ACTIVE, 0
            pygame.draw.circle(
                surface, color, camera.to_screen(handle.position), radius, width
            )

    def _draw_preview_lanes(
        self, surface, camera, path, profile, layer, invalid=False
    ) -> None:
        for index, lane in enumerate(profile.lanes):
            style = style_for(lane.type)
            if style.layer != layer:
                continue
            ribbon = build_ribbon(
                path,
                *profile.lane_bounds(index),
                camera.world_tolerance,
            )
            outline = to_screen_points(camera, ribbon.outline)
            if len(outline) < 3:
                continue
            fill = config.Color.SEGMENT_ERROR if invalid else style.fill
            edge = config.Color.SEGMENT_ERROR if invalid else style.edge
            pygame.draw.polygon(surface, fill, outline)
            if edge is not None:
                pygame.draw.polygon(surface, edge, outline, 1)

    def _draw_snap(self, surface: pygame.Surface, camera: Camera, snap: Snap) -> None:
        """Each snap kind gets its own mark, so what the editor is about to do
        is readable before the click rather than after it."""
        color = SNAP_COLORS[snap.kind]
        center = camera.to_screen(snap.position)
        if snap.kind is SnapKind.NODE:
            pygame.draw.circle(surface, color, center, 9, 2)
        elif snap.kind is SnapKind.ANCHOR:
            direction = snap.anchor.direction
            tip = camera.to_screen(snap.position + direction * 2.0)
            pygame.draw.circle(surface, color, center, 5, 1)
            pygame.draw.line(surface, color, center, tip, 2)
        elif snap.kind is SnapKind.LANE:
            pygame.draw.circle(surface, color, center, 6, 2)
        elif snap.kind is SnapKind.SEGMENT:
            _cross(surface, color, center, 7)  # "this road will be split here"
        elif snap.kind is SnapKind.ANGLE:
            pygame.draw.circle(surface, color, center, 5, 1)
            _cross(surface, color, center, 9)
        else:
            _plus(surface, color, center, 6)


def _cross(
    surface: pygame.Surface, color, center: tuple[float, float], r: float
) -> None:
    x, y = center
    pygame.draw.line(surface, color, (x - r, y - r), (x + r, y + r), 2)
    pygame.draw.line(surface, color, (x - r, y + r), (x + r, y - r), 2)


def _plus(
    surface: pygame.Surface, color, center: tuple[float, float], r: float
) -> None:
    x, y = center
    pygame.draw.line(surface, color, (x - r, y), (x + r, y), 1)
    pygame.draw.line(surface, color, (x, y - r), (x, y + r), 1)


def _dashed_line(
    surface: pygame.Surface,
    color,
    a: tuple[float, float],
    b: tuple[float, float],
    dash: float = 6.0,
) -> None:
    """An alignment guide reads as a hint, not as committed geometry - a solid
    line would look like a road already there."""
    ax, ay = a
    bx, by = b
    length = ((bx - ax) ** 2 + (by - ay) ** 2) ** 0.5
    if length < 1e-6:
        return
    step = dash / length
    t = 0.0
    on = True
    while t < 1.0:
        t_next = min(t + step, 1.0)
        if on:
            pygame.draw.line(
                surface,
                color,
                (ax + (bx - ax) * t, ay + (by - ay) * t),
                (ax + (bx - ax) * t_next, ay + (by - ay) * t_next),
                1,
            )
        on = not on
        t = t_next
