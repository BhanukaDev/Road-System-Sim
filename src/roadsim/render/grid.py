"""Ground grid and world axes. Gives the eye a scale reference while editing."""

from __future__ import annotations

import math

import pygame

from .. import config
from .camera import Camera


def draw_grid(surface: pygame.Surface, camera: Camera) -> None:
    spacing = _adaptive_spacing(camera.zoom)
    lo, hi = camera.world_bounds()
    w, h = camera.viewport

    start_x = math.floor(lo.x / spacing)
    end_x = math.ceil(hi.x / spacing)
    for i in range(start_x, end_x + 1):
        x = i * spacing
        sx, _ = camera.to_screen_xy(x, 0.0)
        color = _line_color(i, x)
        pygame.draw.line(surface, color, (sx, 0), (sx, h))

    start_y = math.floor(lo.y / spacing)
    end_y = math.ceil(hi.y / spacing)
    for i in range(start_y, end_y + 1):
        y = i * spacing
        _, sy = camera.to_screen_xy(0.0, y)
        color = _line_color(i, y, axis=config.Color.AXIS_X)
        pygame.draw.line(surface, color, (0, sy), (w, sy))


def _line_color(index: int, coord: float, axis=config.Color.AXIS_Y):
    if abs(coord) < 1e-9:
        return axis
    if index % config.GRID_MAJOR_EVERY == 0:
        return config.Color.GRID_MAJOR
    return config.Color.GRID_MINOR


_NICE_STEPS = (1.0, 2.0, 5.0)


def _adaptive_spacing(zoom: float) -> float:
    """Smallest 1-2-5 spacing that still leaves grid lines ~14px apart."""
    target = 14.0 / zoom  # metres per 14 screen pixels
    decade = 10.0 ** math.floor(math.log10(max(target, 1e-6)))
    for step in _NICE_STEPS:
        if decade * step >= target:
            return decade * step
    return decade * 10.0
