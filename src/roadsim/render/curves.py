"""Drawing geometry primitives. Read-only: renderers never mutate the model."""

from __future__ import annotations

import pygame

from .. import config
from ..geometry import ArcSegment, Path, Ribbon, Vec2, build_ribbon
from .camera import Camera


def to_screen_points(camera: Camera, points: list[Vec2]) -> list[tuple[float, float]]:
    return [camera.to_screen(p) for p in points]


def draw_path(
    surface: pygame.Surface,
    camera: Camera,
    path: Path,
    color=config.Color.CENTERLINE,
    width: int = 2,
) -> None:
    pts = to_screen_points(camera, path.points(camera.world_tolerance))
    if len(pts) >= 2:
        pygame.draw.lines(surface, color, False, pts, width)


def draw_ribbon(
    surface: pygame.Surface,
    camera: Camera,
    ribbon: Ribbon,
    fill=config.Color.RIBBON_FILL,
    edge=config.Color.RIBBON_EDGE,
    edge_width: int = 1,
) -> None:
    outline = to_screen_points(camera, ribbon.outline)
    if len(outline) < 3:
        return
    if fill is not None:
        pygame.draw.polygon(surface, fill, outline)
    if edge is not None and edge_width > 0:
        pygame.draw.polygon(surface, edge, outline, edge_width)


def draw_path_ribbon(
    surface: pygame.Surface,
    camera: Camera,
    path: Path,
    left: float,
    right: float,
    **kwargs,
) -> Ribbon:
    ribbon = build_ribbon(path, left, right, camera.world_tolerance)
    draw_ribbon(surface, camera, ribbon, **kwargs)
    return ribbon


# -- debug overlays --------------------------------------------------------


def draw_normals(
    surface: pygame.Surface,
    camera: Camera,
    path: Path,
    spacing: float = 5.0,
    length: float = 3.0,
    color=config.Color.NORMAL_TICK,
) -> None:
    """Normal hairs every `spacing` metres. Fanning or crossing hairs mean the
    frame is wrong; evenly spaced ones confirm arc-length parameterisation."""
    for s in _stations(path, spacing):
        frame = path.sample(s)
        a = camera.to_screen(frame.position)
        b = camera.to_screen(frame.position + frame.normal * length)
        pygame.draw.line(surface, color, a, b, 1)


def draw_stations(
    surface: pygame.Surface,
    camera: Camera,
    path: Path,
    spacing: float = 10.0,
    radius: int = 3,
    color=config.Color.STATION_TICK,
) -> None:
    """Dots at fixed arc lengths. Uneven gaps mean the parameterisation drifted."""
    for s in _stations(path, spacing):
        pygame.draw.circle(surface, color, camera.to_screen(path.sample(s).position), radius)


def draw_arc_centers(
    surface: pygame.Surface,
    camera: Camera,
    path: Path,
    color=config.Color.ARC_CENTER,
) -> None:
    """Each arc's centre plus its two radii. Makes tangency failures obvious."""
    for piece, start in zip(path.pieces, path.piece_starts):
        if not isinstance(piece, ArcSegment):
            continue
        c = camera.to_screen(piece.center)
        for end in (piece.start.position, piece.end.position):
            pygame.draw.line(surface, color, c, camera.to_screen(end), 1)
        pygame.draw.circle(surface, color, c, 4, 1)


def _stations(path: Path, spacing: float) -> list[float]:
    if spacing <= 0.0:
        return [0.0, path.length]
    count = int(path.length // spacing)
    return [i * spacing for i in range(count + 1)] + [path.length]
