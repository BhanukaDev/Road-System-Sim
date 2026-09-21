"""Draws one junction: its rounded surface, and any pavement bands its corners
carry.

Extracted from `network_renderer.py` once a junction grew corners and
pavements - a plain polygon fill was the whole of it before M3. A renderer
never mutates the model (D8); this one turns `Junction`/`PavementBand` data
into pygame calls and nothing else.
"""

from __future__ import annotations

import pygame

from .. import config
from ..geometry import Vec2
from ..road.junction import Junction
from ..road.pavement import PavementBand
from .camera import Camera
from .curves import to_screen_points


def draw_junction(surface: pygame.Surface, camera: Camera, junction: Junction) -> None:
    outline = _rounded_outline(junction, camera.world_tolerance)
    if len(outline) < 3:
        return
    points = to_screen_points(camera, outline)
    if junction.is_degenerate:
        # No honest surface here - the mouths overlap, or the ring crosses
        # itself. Filling it anyway is what made a shallow-Y merge look like a
        # rendering glitch instead of geometry that could not be solved, so it
        # is outlined loudly and left unfilled (the same call `is_broken`
        # segments get in `network_renderer`).
        pygame.draw.lines(surface, config.Color.SEGMENT_ERROR, True, points, 2)
        return
    pygame.draw.polygon(surface, config.Color.JUNCTION_FILL, points)


def draw_pavement_band(
    surface: pygame.Surface, camera: Camera, band: PavementBand
) -> None:
    tolerance = camera.world_tolerance
    curb = (
        []
        if band.curb is None
        else [band.curb.sample(s).position for s in band.curb.flatten(tolerance)]
    )
    inner = (
        []
        if band.inner is None
        else [band.inner.sample(s).position for s in band.inner.flatten(tolerance)]
    )
    outline = [
        band.outer_start,
        *curb,
        band.outer_end,
        band.inner_end,
        *reversed(inner),
        band.inner_start,
    ]
    points = to_screen_points(camera, outline)
    if len(points) < 3:
        return
    pygame.draw.polygon(surface, config.Color.LANE_SIDEWALK, points)


def _rounded_outline(junction: Junction, tolerance: float) -> list[Vec2]:
    """Walk the mouths counter-clockwise, replacing each straight corner cut
    with its fillet's own arc where there is one.

    `junction.polygon` already holds two points per end - `(right, left)` at
    that end's own trimmed mouth (`build_junction`'s `_polygon`) - and
    `junction.corners[i]` rounds exactly the gap between end `i`'s `left` and
    end `i + 1`'s `right`: the two points either side of the straight cut this
    replaces. No corner - a kink squeezed below `MIN_RADIUS`, or no room at
    all - leaves that cut as it was.
    """
    n = len(junction.ends)
    if len(junction.polygon) != 2 * n:
        return list(junction.polygon)
    outline: list[Vec2] = []
    for i in range(n):
        outline.append(junction.polygon[2 * i])
        outline.append(junction.polygon[2 * i + 1])
        fillet = junction.corners[i] if i < len(junction.corners) else None
        if fillet is not None:
            outline.extend(
                fillet.arc.sample(s).position for s in fillet.arc.flatten(tolerance)
            )
    return outline
