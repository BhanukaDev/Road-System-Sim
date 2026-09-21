"""Draws a crosswalk's zebra stripes and its stop line.

`road/crosswalk.py` decides the span; colour is here, the same split
`lane_markings.py` makes between what goes where and what it looks like. Both
are painted the same way a lane is - offset ribbons off the centreline, never
resampled - so they bend with the same curve the kerb does.
"""

from __future__ import annotations

import pygame

from .. import config
from ..geometry import Path, build_ribbon
from ..road.crosswalk import CrosswalkMark
from .camera import Camera
from .curves import to_screen_points


def draw_crosswalk(
    surface: pygame.Surface, camera: Camera, path: Path, mark: CrosswalkMark
) -> None:
    tolerance = camera.world_tolerance
    half_stripe = config.CROSSWALK_STRIPE_WIDTH / 2.0
    period = config.CROSSWALK_STRIPE_WIDTH + config.CROSSWALK_STRIPE_GAP

    offset = mark.right + half_stripe
    while offset <= mark.left + 1e-6:
        _draw_band(
            surface,
            camera,
            path,
            tolerance,
            offset + half_stripe,
            offset - half_stripe,
            mark.stripes_s0,
            mark.stripes_s1,
        )
        offset += period

    # The stop line holds back the approach half only, never the full width the
    # stripes cover - see `CrosswalkMark.stop_left`.
    if not mark.has_stop_line:
        return
    half_stop = config.STOP_LINE_THICKNESS / 2.0
    _draw_band(
        surface,
        camera,
        path,
        tolerance,
        mark.stop_left,
        mark.stop_right,
        mark.stop_s - half_stop,
        mark.stop_s + half_stop,
    )


def _draw_band(
    surface: pygame.Surface,
    camera: Camera,
    path: Path,
    tolerance: float,
    left: float,
    right: float,
    s0: float,
    s1: float,
) -> None:
    ribbon = build_ribbon(path, left, right, tolerance, s0, s1)
    points = to_screen_points(camera, ribbon.outline)
    if len(points) >= 3:
        pygame.draw.polygon(surface, config.Color.MARKING_WHITE, points)
