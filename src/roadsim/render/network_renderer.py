"""Draws a `RoadNetwork`. Read-only: a renderer never mutates the model.

Order matters and is fixed here: lane ribbons bottom-up by layer, then junction
surfaces filling the gaps the trims opened, then direction arrows on top. Lane
colours are not decided here - `lane_style.py` owns that mapping, so a new lane
type never touches this file.

Every ribbon is built at `camera.world_tolerance`, so the geometry gets finer as
you zoom in and cheaper as you zoom out (D7).
"""

from __future__ import annotations

import pygame

from .. import config
from ..geometry import Vec2
from ..road import RoadNetwork, RoadSegment
from ..road.cap import Cap, CapKind
from ..road.lane import Direction
from .camera import Camera
from .curves import to_screen_points
from .lane_style import LAYERS, style_for


class NetworkRenderer:
    def __init__(self, show_arrows: bool = True) -> None:
        self.show_arrows = show_arrows

    def draw(
        self, surface: pygame.Surface, camera: Camera, network: RoadNetwork
    ) -> None:
        drawable = [s for s in network.segments.values() if not s.is_broken]

        for layer in LAYERS:
            for segment in drawable:
                self._draw_lanes(surface, camera, segment, layer)

        for junction in network.junctions.values():
            self._draw_polygon(surface, camera, junction.polygon)

        for cap in network.caps.values():
            self._draw_cap(surface, camera, cap)

        if self.show_arrows:
            for segment in drawable:
                self._draw_arrows(surface, camera, segment)

        for segment in network.segments.values():
            if segment.is_broken:
                self._draw_error(surface, camera, segment)

    # -- pieces ------------------------------------------------------------

    def _draw_lanes(
        self,
        surface: pygame.Surface,
        camera: Camera,
        segment: RoadSegment,
        layer: int,
    ) -> None:
        tolerance = camera.world_tolerance
        for k, lane in enumerate(segment.profile.lanes):
            style = style_for(lane.type)
            if style.layer != layer:
                continue
            outline = to_screen_points(
                camera, segment.lane_ribbon(k, tolerance).outline
            )
            if len(outline) < 3:
                continue
            pygame.draw.polygon(surface, style.fill, outline)
            if style.edge is not None:
                pygame.draw.polygon(surface, style.edge, outline, 1)

    def _draw_polygon(
        self, surface: pygame.Surface, camera: Camera, polygon: tuple[Vec2, ...]
    ) -> None:
        if len(polygon) < 3:
            return
        points = to_screen_points(camera, list(polygon))
        pygame.draw.polygon(surface, config.Color.JUNCTION_FILL, points)
        pygame.draw.polygon(surface, config.Color.JUNCTION_EDGE, points, 1)

    def _draw_cap(self, surface: pygame.Surface, camera: Camera, cap: Cap) -> None:
        if cap.kind is CapKind.TERMINAL:
            points = to_screen_points(camera, [cap.left, cap.right])
            pygame.draw.lines(
                surface,
                config.Color.STOP_LINE,
                False,
                points,
                max(1, round(config.STOP_LINE_WIDTH_PX)),
            )
            return
        bulge = cap.bulge
        arc_points = [
            bulge.sample(s).position for s in bulge.flatten(camera.world_tolerance)
        ]
        points = to_screen_points(camera, [cap.left, *arc_points, cap.right])
        if len(points) < 3:
            return
        pygame.draw.polygon(surface, config.Color.CAP_FILL, points)
        pygame.draw.polygon(surface, config.Color.CAP_EDGE, points, 1)

    def _draw_arrows(
        self, surface: pygame.Surface, camera: Camera, segment: RoadSegment
    ) -> None:
        """Travel-direction chevrons, spaced along the centreline's arc length.

        Spacing comes off the centreline rather than each lane's own offset
        path, which is what keeps the arrows in a multi-lane curve lined up
        across the road instead of drifting apart lane by lane.
        """
        if segment.carriageway_length * camera.zoom < config.DIRECTION_ARROW_MIN_PX:
            return
        profile = segment.profile
        stations = _stations(
            segment.trim_a,
            segment.path.length - segment.trim_b,
            config.DIRECTION_ARROW_SPACING,
        )
        half = config.DIRECTION_ARROW_LENGTH / 2.0
        for k, lane in enumerate(profile.lanes):
            if not lane.type.carries_vehicles or not lane.direction.is_traffic:
                continue
            offset = profile.lane_center(k)
            signs = _arrow_signs(lane.direction)
            # A two-way lane gets its arrows nose to nose rather than stacked on
            # one point, where they would read as a bowtie instead of two arrows.
            spread = half * 1.3 if len(signs) > 1 else 0.0
            for s in stations:
                for sign in signs:
                    frame = segment.path.sample(s + sign * spread)
                    center = frame.position + frame.normal * offset
                    self._draw_arrow(
                        surface, camera, center, frame.tangent * sign, half, lane.width
                    )

    def _draw_arrow(
        self,
        surface: pygame.Surface,
        camera: Camera,
        center: Vec2,
        direction: Vec2,
        half: float,
        lane_width: float,
    ) -> None:
        wing = min(lane_width * 0.22, half * 0.8)
        tip = center + direction * half
        base = center - direction * half
        side = direction.rot90() * wing
        points = to_screen_points(camera, [tip, base + side, base - side])
        pygame.draw.polygon(surface, config.Color.DIRECTION_ARROW, points)

    def _draw_error(
        self, surface: pygame.Surface, camera: Camera, segment: RoadSegment
    ) -> None:
        """A segment that cannot be drawn as a road - eaten by its junctions, or
        curved tighter than its own width allows. Drawn, loudly, as a centreline
        rather than silently skipped: the user needs to see where it went."""
        points = to_screen_points(camera, segment.path.points(camera.world_tolerance))
        if len(points) >= 2:
            pygame.draw.lines(surface, config.Color.SEGMENT_ERROR, False, points, 3)


def _arrow_signs(direction: Direction) -> tuple[float, ...]:
    if direction is Direction.FORWARD:
        return (1.0,)
    if direction is Direction.BACKWARD:
        return (-1.0,)
    return (1.0, -1.0)


def _stations(s0: float, s1: float, spacing: float) -> list[float]:
    """Evenly spaced arc lengths, centred in the span so both ends stay clear."""
    span = s1 - s0
    count = int(span // spacing)
    if count < 1:
        return [s0 + span / 2.0] if span > 0.0 else []
    start = s0 + (span - (count - 1) * spacing) / 2.0
    return [start + i * spacing for i in range(count)]
