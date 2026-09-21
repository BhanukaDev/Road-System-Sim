"""Draws lane markings: solid or dashed strips offset from the centreline.

`road/markings.py` decides what line goes where and whether it is broken; this
decides colour, exactly the split `lane_style.py` makes for lane fills. A
marking is a filled ribbon `MARKING_WIDTH` wide, the same construction a lane
edge or a crosswalk stripe is built with - world-space width rather than a
fixed screen-pixel stroke, so paint stays the same size relative to the road at
any zoom, and bends with the same curve the lane edges do.
"""

from __future__ import annotations

import pygame

from .. import config
from ..geometry import Path, build_ribbon
from ..road.markings import MarkingKind, lane_markings
from ..road.profile import RoadProfile
from .camera import Camera
from .curves import to_screen_points

MARKING_COLOR: dict[MarkingKind, tuple[int, int, int]] = {
    MarkingKind.LANE_DIVIDER: config.Color.MARKING_WHITE,
    MarkingKind.CENTER_LINE: config.Color.MARKING_YELLOW,
    MarkingKind.MEDIAN_EDGE: config.Color.MARKING_YELLOW,
    MarkingKind.EDGE_LINE: config.Color.MARKING_WHITE,
}


def draw_markings(
    surface: pygame.Surface,
    camera: Camera,
    path: Path,
    profile: RoadProfile,
    s0: float,
    s1: float,
    narrowed: dict[float, tuple[float, float]] | None = None,
) -> None:
    """`narrowed` shortens *one* marking's own span, keyed by its offset.

    A median taper (`road/median_taper.py`) narrows the lane's own edges short
    of the mouth, and paints its own converging line over that stretch - so
    the plain straight edge line this function would otherwise draw the whole
    way to the mouth has to stop where the taper starts, or the two lines run
    on top of each other."""
    if s1 - s0 < 1e-6 or (s1 - s0) * camera.zoom < config.MARKING_MIN_PX:
        return
    tolerance = camera.world_tolerance
    half_width = config.MARKING_WIDTH / 2.0
    for marking in lane_markings(profile):
        color = MARKING_COLOR[marking.kind]
        left, right = marking.offset + half_width, marking.offset - half_width
        span = (narrowed or {}).get(round(marking.offset, 9), (s0, s1))
        m_s0, m_s1 = span
        if m_s1 - m_s0 < 1e-6:
            continue
        if marking.kind.is_dashed:
            for dash_s0, dash_s1 in dash_intervals(m_s0, m_s1):
                _draw_band(
                    surface,
                    camera,
                    path,
                    tolerance,
                    left,
                    right,
                    dash_s0,
                    dash_s1,
                    color,
                )
        else:
            _draw_band(surface, camera, path, tolerance, left, right, m_s0, m_s1, color)


def _draw_band(
    surface: pygame.Surface,
    camera: Camera,
    path: Path,
    tolerance: float,
    left: float,
    right: float,
    s0: float,
    s1: float,
    color: tuple[int, int, int],
) -> None:
    ribbon = build_ribbon(path, left, right, tolerance, s0, s1)
    points = to_screen_points(camera, ribbon.outline)
    if len(points) >= 3:
        pygame.draw.polygon(surface, color, points)


def dash_intervals(s0: float, s1: float) -> list[tuple[float, float]]:
    """(start, end) arc-length spans of paint, phase-locked to the centreline
    itself (not to `s0`) so a dash never jumps as a junction's trim changes."""
    period = config.MARKING_DASH_LENGTH + config.MARKING_GAP_LENGTH
    out: list[tuple[float, float]] = []
    s = (s0 // period) * period
    while s < s1:
        d0, d1 = max(s, s0), min(s + config.MARKING_DASH_LENGTH, s1)
        if d1 > d0:
            out.append((d0, d1))
        s += period
    return out
    return p0 + (p1 - p0) * t
