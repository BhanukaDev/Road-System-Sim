"""Draws the paint across a lane-count transition.

`road/transition.py` decides what line goes where; colour, dash phase and the
too-small-to-bother threshold come from `lane_markings.py` so a line carried
across a patch looks like the same line that stops at either mouth - which is
the whole point of drawing it.
"""

from __future__ import annotations

import pygame

from .. import config
from ..geometry import build_ribbon
from ..road.decal import get as decal_for
from ..road.transition import LaneTransition, TransitionMarking
from .camera import Camera
from .curves import to_screen_points
from .decal_renderer import draw_decal
from .lane_markings import MARKING_COLOR, dash_intervals


def draw_transition(
    surface: pygame.Surface, camera: Camera, transition: LaneTransition
) -> None:
    tolerance = camera.world_tolerance
    half_width = config.MARKING_WIDTH / 2.0
    for marking in transition.markings:
        if marking.curve.length * camera.zoom < config.MARKING_MIN_PX:
            continue
        color = MARKING_COLOR[marking.kind]
        if marking.kind.is_dashed:
            _dashed(surface, camera, marking, tolerance, half_width, color)
        else:
            _band(
                surface,
                camera,
                marking.curve,
                tolerance,
                half_width,
                color,
                0.0,
                marking.curve.length,
            )

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


def _band(surface, camera, curve, tolerance, half_width, color, s0, s1) -> None:
    ribbon = build_ribbon(curve, half_width, -half_width, tolerance, s0, s1)
    points = to_screen_points(camera, ribbon.outline)
    if len(points) >= 3:
        pygame.draw.polygon(surface, color, points)


def _dashed(
    surface, camera, marking: TransitionMarking, tolerance, half_width, color
) -> None:
    """Dashes run from the patch's own start rather than from the road's arc
    length, because a transition is not on any one segment's parameterisation -
    there is no shared `s` across the gap to phase-lock to."""
    curve = marking.curve
    for d0, d1 in dash_intervals(0.0, curve.length):
        _band(surface, camera, curve, tolerance, half_width, color, d0, d1)
