"""Draws a painted decal - `road/decal.py` owns the shape, this owns the paint.

The same split `lane_markings.py` and `crosswalk_renderer.py` already make: what
goes where is a road question, what colour it is and when it is too small to be
worth drawing are rendering ones.
"""

from __future__ import annotations

import pygame

from .. import config
from ..geometry import Vec2
from ..road.decal import Decal
from .camera import Camera
from .curves import to_screen_points


def draw_decal(
    surface: pygame.Surface,
    camera: Camera,
    decal: Decal,
    position: Vec2,
    forward: Vec2,
    length: float,
    color: tuple[int, int, int] = config.Color.MARKING_WHITE,
) -> None:
    """Skipped rather than crammed below `MARKING_MIN_PX`, the same threshold
    lane markings and direction arrows use - a marking too small to read is
    noise on the road, not information."""
    if length * camera.zoom < config.MARKING_MIN_PX:
        return
    for ring in decal.placed(position, forward, length):
        points = to_screen_points(camera, ring)
        if len(points) >= 3:
            pygame.draw.polygon(surface, color, points)
