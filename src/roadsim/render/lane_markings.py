"""Draws lane markings: solid or dashed strips offset from the centreline.

`road/markings.py` decides what line goes where and whether it is broken; this
decides colour, exactly the split `lane_style.py` makes for lane fills. A
marking is built the same way a lane edge is - `build_ribbon` with equal left
and right offsets collapses to a single offset polyline - so paint bends with
the same curve the lane edges do, and stops exactly at the carriageway span a
segment's junctions have already trimmed it to, at any meeting angle.
"""

from __future__ import annotations

import bisect

import pygame

from .. import config
from ..geometry import Path, Vec2, build_ribbon
from ..road.markings import MarkingKind, lane_markings
from ..road.profile import RoadProfile
from .camera import Camera
from .curves import to_screen_points

_COLOR: dict[MarkingKind, tuple[int, int, int]] = {
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
) -> None:
    if s1 - s0 < 1e-6 or (s1 - s0) * camera.zoom < config.MARKING_MIN_PX:
        return
    tolerance = camera.world_tolerance
    for marking in lane_markings(profile):
        ribbon = build_ribbon(path, marking.offset, marking.offset, tolerance, s0, s1)
        stations = [section.s for section in ribbon.sections]
        points = [section.left for section in ribbon.sections]
        color = _COLOR[marking.kind]
        if marking.kind.is_dashed:
            _draw_dashed(surface, camera, stations, points, color)
        else:
            screen = to_screen_points(camera, points)
            if len(screen) >= 2:
                pygame.draw.lines(
                    surface, color, False, screen, round(config.MARKING_WIDTH_PX)
                )


def _draw_dashed(
    surface: pygame.Surface,
    camera: Camera,
    stations: list[float],
    points: list[Vec2],
    color: tuple[int, int, int],
) -> None:
    if len(stations) < 2:
        return
    s0, s1 = stations[0], stations[-1]
    width = round(config.MARKING_WIDTH_PX)
    for dash_s0, dash_s1 in _dash_intervals(s0, s1):
        strip = [
            _point_at(stations, points, s)
            for s in _boundaries_in(stations, dash_s0, dash_s1)
        ]
        screen = to_screen_points(camera, strip)
        if len(screen) >= 2:
            pygame.draw.lines(surface, color, False, screen, width)


def _dash_intervals(s0: float, s1: float) -> list[tuple[float, float]]:
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


def _boundaries_in(stations: list[float], lo: float, hi: float) -> list[float]:
    """`lo`, every station strictly between, and `hi` - so a dash follows the
    same flattened curve the lane edges do instead of cutting its corner."""
    i = bisect.bisect_right(stations, lo)
    j = bisect.bisect_left(stations, hi)
    return [lo, *stations[i:j], hi]


def _point_at(stations: list[float], points: list[Vec2], s: float) -> Vec2:
    i = bisect.bisect_left(stations, s)
    if i < len(stations) and abs(stations[i] - s) < 1e-9:
        return points[i]
    i = max(1, min(i, len(stations) - 1))
    s0, s1 = stations[i - 1], stations[i]
    t = 0.0 if s1 - s0 < 1e-9 else (s - s0) / (s1 - s0)
    p0, p1 = points[i - 1], points[i]
    return p0 + (p1 - p0) * t
