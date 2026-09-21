"""Draws the paint across a lane-count transition.

`road/transition.py` decides what line goes where; colour, dash phase and the
too-small-to-bother threshold come from `lane_markings.py` so a line carried
across a patch looks like the same line that stops at either mouth - which is
the whole point of drawing it.
"""

from __future__ import annotations

import pygame

from .. import config
from ..road.decal import get as decal_for
from ..road.transition import LaneTransition
from .camera import Camera
from .curves import to_screen_points
from .decal_renderer import draw_decal
from .lane_markings import MARKING_COLOR, dash_intervals


def draw_transition(
    surface: pygame.Surface, camera: Camera, transition: LaneTransition
) -> None:
    width = max(1, round(config.MARKING_WIDTH_PX))
    for marking in transition.markings:
        span = marking.start.distance_to(marking.end)
        if span * camera.zoom < config.MARKING_MIN_PX:
            continue
        color = MARKING_COLOR[marking.kind]
        if marking.kind.is_dashed:
            _dashed(surface, camera, marking, span, color, width)
        else:
            _solid(surface, camera, marking, color, width)

    for arrow in transition.arrows:
        decal = decal_for(arrow.decal)
        draw_decal(
            surface,
            camera,
            decal,
            arrow.position,
            arrow.forward,
            decal.fitted_length(
                config.TRANSITION_ARROW_LENGTH,
                arrow.lane_width * config.TRANSITION_ARROW_LANE_FRACTION,
            ),
        )


def _solid(surface, camera, marking, color, width) -> None:
    points = to_screen_points(camera, [marking.start, marking.end])
    if len(points) >= 2:
        pygame.draw.lines(surface, color, False, points, width)


def _dashed(surface, camera, marking, span, color, width) -> None:
    """Dashes run from the patch's own start rather than from the road's arc
    length, because a transition is not on any one segment's parameterisation -
    there is no shared `s` across the gap to phase-lock to."""
    direction = (marking.end - marking.start) / span
    for d0, d1 in dash_intervals(0.0, span):
        points = to_screen_points(
            camera, [marking.start + direction * d0, marking.start + direction * d1]
        )
        if len(points) >= 2:
            pygame.draw.lines(surface, color, False, points, width)
