"""Draws a median's taper to a crossing: the narrowing island, the constant-
width refuge it carries into the crosswalk, the converging edge lines and the
gore hatch painted in the width the taper gives up either side.

`road/median_taper.py` decides where; this turns it into pygame calls, the
same split every other marking in this codebase makes.
"""

from __future__ import annotations

import pygame

from .. import config
from ..geometry import build_ribbon
from ..road.decal import get as decal_for
from ..road.median_taper import MedianTaper
from .camera import Camera
from .curves import to_screen_points
from .decal_renderer import draw_decal


def draw_median_taper(
    surface: pygame.Surface, camera: Camera, taper: MedianTaper
) -> None:
    for polygon in taper.gores:
        points = to_screen_points(camera, polygon)
        if len(points) >= 3:
            pygame.draw.polygon(surface, config.Color.LANE_CAR, points)

    for polygon in (taper.island, taper.refuge):
        points = to_screen_points(camera, polygon)
        if len(points) >= 3:
            pygame.draw.polygon(surface, config.Color.LANE_MEDIAN, points)

    half_width = config.MARKING_WIDTH / 2.0
    tolerance = camera.world_tolerance
    for edge in taper.edges:
        if edge.length * camera.zoom < config.MARKING_MIN_PX:
            continue
        ribbon = build_ribbon(
            edge, half_width, -half_width, tolerance, 0.0, edge.length
        )
        edge_points = to_screen_points(camera, ribbon.outline)
        if len(edge_points) >= 3:
            pygame.draw.polygon(surface, config.Color.MARKING_YELLOW, edge_points)

    for hatch in taper.hatches:
        decal = decal_for(hatch.decal)
        draw_decal(surface, camera, decal, hatch.position, hatch.forward, hatch.length)
