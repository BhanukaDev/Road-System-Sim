"""Everything the editor draws on top of the network.

Tools produce a `ToolPreview` as geometry; this file is the only place in
`editor/` that turns anything into pixels. It reads the model and the preview
and mutates neither - the same read-only contract the renderers in `render/`
work under (D8).

Two layers. Handles, snap marks, guides and readouts are drawn straight onto
the frame, opaque, because they are *instruments* and have to stay crisp. The
ghost - the road a commit would build, the road being hovered, the footprint
disc before a first click - is drawn onto a separate per-pixel-alpha surface
and blitted through once, translucent (D22). One surface, one alpha: two
translucent polygons drawn separately would darken where they overlap and a
lane boundary would read as a seam. When the ghost cannot be built the whole
layer is tinted red before the blit, so a rejected road stays a road - lanes,
junction, caps - and simply reads as the wrong colour, which is what a game
player already knows how to read.
"""

from __future__ import annotations

from collections.abc import Callable

import pygame

from .. import config
from ..geometry import Path, Vec2, build_ribbon
from ..render.camera import Camera
from ..render.curves import to_screen_points
from ..render.lane_markings import draw_markings
from ..render.lane_style import LAYERS, style_for
from ..render.network_renderer import NetworkRenderer
from ..road.network import RoadNetwork
from ..road.profile import RoadProfile
from .context import Selection, ToolPreview
from .ghost import Ghost
from .handle import HandleKind, PreviewHandle
from .highlight import Highlight, HighlightKind
from .snapping import Snap, SnapKind

SNAP_COLORS = {
    SnapKind.NODE: config.Color.SNAP_NODE,
    SnapKind.ANCHOR: config.Color.SNAP_ANCHOR,
    SnapKind.BESIDE: config.Color.SNAP_BESIDE,
    SnapKind.SEGMENT: config.Color.SNAP_SEGMENT,
    SnapKind.ANGLE: config.Color.SNAP_ANGLE,
    SnapKind.GRID: config.Color.SNAP_GRID,
}

HANDLE_STYLES: dict[HandleKind, tuple[tuple[int, int, int], int, int]] = {
    HandleKind.CONTROL: (config.Color.HANDLE_CONTROL, 5, 0),
    HandleKind.ARC_MID: (config.Color.HANDLE_DERIVED, 4, 1),
    HandleKind.ARC_END: (config.Color.HANDLE_DERIVED, 3, 1),
    HandleKind.STRAIGHT_MID: (config.Color.HANDLE_DERIVED, 3, 1),
}
"""Colour, screen radius and outline width per handle kind. A registry rather
than a branch: a new kind is one line here and it appears on screen."""

_FONT: dict[int, pygame.font.Font] = {}


def _font(size: int = 12) -> pygame.font.Font:
    """One font object per size, made on first use - `SysFont` reads the disk,
    and the old code did that for every label on every frame."""
    font = _FONT.get(size)
    if font is None:
        font = _FONT[size] = pygame.font.SysFont("consolas,menlo,monospace", size)
    return font


class EditorOverlay:
    def __init__(self, show_nodes: bool = True) -> None:
        self.show_nodes = show_nodes
        self.show_control_points = False
        self._ghost_renderer = NetworkRenderer(show_arrows=False)
        """Draws the ghost's subset of its network. Direction chevrons are an
        editing aid over the *real* network; on a ghost they only add noise."""
        self._layer: pygame.Surface | None = None
        """The translucent layer, kept between frames and remade on resize."""

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
        self._draw_ghost_layer(surface, camera, network, preview)
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
        """The selected road is washed over its whole carriageway in the
        selection colour - the same shape the hover wash takes, so "this is
        lit" and "this is chosen" read as the same thing in two colours."""
        if selection.segment is None or selection.segment not in network.segments:
            return
        segment = network.segments[selection.segment]
        outline = _carriageway_outline(camera, segment)
        if len(outline) >= 3:
            pygame.draw.polygon(
                surface, config.Color.SELECTION, outline, 2
            )
            layer = self._layer_for(surface)
            layer.fill((0, 0, 0, 0))
            pygame.draw.polygon(
                layer, (*config.Color.SELECTION, config.SELECTION_ALPHA), outline
            )
            layer.set_alpha(255)
            surface.blit(layer, (0, 0))

    # -- the translucent layer --------------------------------------------

    def _draw_ghost_layer(
        self,
        surface: pygame.Surface,
        camera: Camera,
        network: RoadNetwork,
        preview: ToolPreview,
    ) -> None:
        """Hover washes, the footprint disc and the ghost road, through one
        alpha. Skipped entirely when there is nothing to put on it, so a tool
        that offers none of these costs no full-window clear per frame."""
        has_ghost = preview.ghost is not None or (
            preview.profile is not None and preview.paths
        )
        if not (has_ghost or preview.highlights or preview.footprint):
            return
        layer = self._layer_for(surface)
        layer.fill((0, 0, 0, 0))

        for highlight in preview.highlights:
            self._draw_highlight(layer, camera, network, highlight)
        if preview.footprint is not None and preview.profile is not None:
            self._draw_footprint(layer, camera, preview.footprint, preview.profile)
        layer.set_alpha(255)
        surface.blit(layer, (0, 0))

        if not has_ghost:
            return
        layer.fill((0, 0, 0, 0))
        if preview.ghost is not None:
            self._draw_ghost(layer, camera, preview.ghost)
        elif preview.profile is not None:
            for path in preview.paths:
                self._draw_ghost_road(layer, camera, path, preview.profile)
        if preview.invalid:
            layer.fill(config.Color.GHOST_INVALID_TINT, special_flags=pygame.BLEND_RGB_ADD)
        layer.set_alpha(config.GHOST_ALPHA)
        surface.blit(layer, (0, 0))

    def _layer_for(self, surface: pygame.Surface) -> pygame.Surface:
        if self._layer is None or self._layer.get_size() != surface.get_size():
            self._layer = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
        return self._layer

    def _draw_ghost(self, layer: pygame.Surface, camera: Camera, ghost: Ghost) -> None:
        """The ghost network's changed subset, through the real renderer - so a
        ghost junction is drawn by the code that will draw the junction."""
        self._ghost_renderer.draw(
            layer, camera, ghost.network, ghost.segments, ghost.nodes
        )

    def _draw_ghost_road(
        self, layer: pygame.Surface, camera: Camera, path: Path, profile: RoadProfile
    ) -> None:
        """A road that has no ghost network to live in - refused before it
        could be built, or offered by a tool that only has a path. Lanes and
        markings, the way the real renderer lays them, minus any junction."""
        for lane_layer in LAYERS:
            for index, lane in enumerate(profile.lanes):
                style = style_for(lane.type)
                if style.layer != lane_layer:
                    continue
                ribbon = build_ribbon(
                    path, *profile.lane_bounds(index), camera.world_tolerance
                )
                outline = to_screen_points(camera, ribbon.outline)
                if len(outline) < 3:
                    continue
                pygame.draw.polygon(layer, style.fill, outline)
                if style.edge is not None:
                    pygame.draw.polygon(layer, style.edge, outline, 1)
        draw_markings(layer, camera, path, profile, 0.0, path.length)

    def _draw_highlight(
        self,
        layer: pygame.Surface,
        camera: Camera,
        network: RoadNetwork,
        highlight: Highlight,
    ) -> None:
        wash = (*config.Color.HOVER, config.HOVER_ALPHA)
        if highlight.kind is HighlightKind.SEGMENT:
            segment = network.segments.get(highlight.id)
            if segment is None:
                return
            if segment.is_broken:
                return  # drawn as an error line already; nothing to wash
            outline = _carriageway_outline(camera, segment)
            if len(outline) >= 3:
                pygame.draw.polygon(layer, wash, outline)
                pygame.draw.polygon(layer, config.Color.HOVER, outline, 2)
        elif highlight.kind is HighlightKind.NODE:
            node = network.nodes.get(highlight.id)
            if node is None:
                return
            radius = _node_radius(network, node.id) * camera.zoom
            center = camera.to_screen(node.position)
            pygame.draw.circle(layer, wash, center, max(radius, 6.0))
            pygame.draw.circle(layer, config.Color.HOVER, center, max(radius, 6.0), 2)

    def _draw_footprint(
        self, layer: pygame.Surface, camera: Camera, at: Vec2, profile: RoadProfile
    ) -> None:
        """The road's width where its body would be, before there is a road to
        show. `at` is the body's centre - which is the cursor in open space and
        sits beside the centreline when a lane is being aimed at - so the
        radius is half the body, not the wider of the two extents."""
        radius = max(profile.total_width / 2.0 * camera.zoom, 3.0)
        center = camera.to_screen(at)
        pygame.draw.circle(
            layer, (*config.Color.FOOTPRINT, config.FOOTPRINT_ALPHA), center, radius
        )
        pygame.draw.circle(layer, config.Color.FOOTPRINT, center, radius, 1)

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

        if preview.profile is None:
            # A bare path, no cross-section to make a ghost of - the one case
            # the centreline is the whole road.
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
            label = _font().render(
                f"{preview.measurement:.1f} m", True, config.Color.HUD_TEXT
            )
            surface.blit(label, (x + 8, y - 8))

        for readout in preview.angles:
            x, y = camera.to_screen(readout.position)
            label = _font().render(
                f"{readout.degrees:.0f} deg", True, config.Color.HUD_TEXT
            )
            surface.blit(label, (x + 8, y + 8))

        if preview.invalid and preview.reason:
            self._draw_reason(surface, camera, preview)

        self._draw_handles(surface, camera, preview.handles)

        if preview.snap is not None:
            self._draw_snap(surface, camera, preview.snap)

    def _draw_reason(
        self, surface: pygame.Surface, camera: Camera, preview: ToolPreview
    ) -> None:
        """Why the ghost is red, next to the thing that is wrong when the
        problem has a place, else at the road's live end - where the eye is."""
        at = None
        if preview.ghost is not None and preview.ghost.problem is not None:
            at = preview.ghost.problem.position
        if at is None and preview.paths:
            at = preview.paths[-1].end.position
        if at is None and preview.points:
            at = preview.points[-1]
        if at is None:
            return
        x, y = camera.to_screen(at)
        label = _font().render(preview.reason, True, config.Color.HUD_TEXT)
        pad = 4
        box = label.get_rect().inflate(pad * 2, pad * 2).move(x + 10, y - 26)
        pygame.draw.rect(surface, config.Color.SEGMENT_ERROR, box, border_radius=3)
        surface.blit(label, (box.x + pad, box.y + pad))

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

    def _draw_snap(self, surface: pygame.Surface, camera: Camera, snap: Snap) -> None:
        """Each snap kind gets its own mark, so what the editor is about to do
        is readable before the click rather than after it."""
        SNAP_MARKS[snap.kind](surface, SNAP_COLORS[snap.kind], camera, snap)


# -- snap marks, one per kind ------------------------------------------------


def _mark_node(surface, color, camera: Camera, snap: Snap) -> None:
    pygame.draw.circle(surface, color, camera.to_screen(snap.position), 9, 2)


def _mark_anchor(surface, color, camera: Camera, snap: Snap) -> None:
    center = camera.to_screen(snap.position)
    tip = camera.to_screen(snap.position + snap.anchor.direction * 2.0)
    pygame.draw.circle(surface, color, center, 5, 1)
    pygame.draw.line(surface, color, center, tip, 2)


def _mark_beside(surface, color, camera: Camera, snap: Snap) -> None:
    """A dashed run along the kerb the point was laid against, and the point
    itself: the alignment is the line, so the line is what is drawn."""
    hit = snap.beside
    reach = config.BESIDE_MARK_PX / camera.zoom  # metres; the camera flips y
    _dashed_line(
        surface,
        color,
        camera.to_screen(hit.kerb - hit.tangent * reach),
        camera.to_screen(hit.kerb + hit.tangent * reach),
    )
    pygame.draw.circle(surface, color, camera.to_screen(snap.position), 5, 1)


def _mark_segment(surface, color, camera: Camera, snap: Snap) -> None:
    _cross(surface, color, camera.to_screen(snap.position), 7)  # "split here"


def _mark_angle(surface, color, camera: Camera, snap: Snap) -> None:
    center = camera.to_screen(snap.position)
    pygame.draw.circle(surface, color, center, 5, 1)
    _cross(surface, color, center, 9)


def _mark_grid(surface, color, camera: Camera, snap: Snap) -> None:
    _plus(surface, color, camera.to_screen(snap.position), 6)


SNAP_MARKS: dict[SnapKind, Callable[..., None]] = {
    SnapKind.NODE: _mark_node,
    SnapKind.ANCHOR: _mark_anchor,
    SnapKind.BESIDE: _mark_beside,
    SnapKind.SEGMENT: _mark_segment,
    SnapKind.ANGLE: _mark_angle,
    SnapKind.GRID: _mark_grid,
}
"""How each snap kind is marked. A new kind is one function and one line here,
the same shape as `HANDLE_STYLES`."""


def _carriageway_outline(camera: Camera, segment) -> list[tuple[float, float]]:
    """The screen polygon of a road's carriageway between its trims."""
    if segment.is_broken:
        return []
    ribbon = build_ribbon(
        segment.path,
        segment.profile.extent_left,
        -segment.profile.extent_right,
        camera.world_tolerance,
        s0=segment.trim_a,
        s1=segment.path.length - segment.trim_b,
    )
    return to_screen_points(camera, ribbon.outline)


def _node_radius(network: RoadNetwork, node_id: int) -> float:
    """Metres: the widest half-width meeting at a node, so a hover ring on a
    junction covers the junction and one on a lone joint covers its road."""
    node = network.nodes[node_id]
    widths = [
        network.segments[sid].profile.half_width
        for sid in node.segments
        if sid in network.segments
    ]
    return max(widths, default=0.0)


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
