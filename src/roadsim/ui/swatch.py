"""A road profile drawn as a little cross-section.

This is the one place `ui` reaches into `render`, and it reaches for exactly one
thing: `lane_style.style_for`. Widths come from the profile's own lanes, colours
from the only table that is allowed to hold them. A road button therefore teaches
what the road *is* - four lanes with a median, or two lanes and a pavement each
side - rather than just naming it.

`swatch_rects` is deliberately separate from the drawing: it is pure arithmetic,
so the layout is tested exactly, with no display open.
"""

from __future__ import annotations

import pygame

from .. import config
from ..render.lane_style import style_for
from ..road.profile import RoadProfile


def swatch_rects(rect: pygame.Rect, profile: RoadProfile) -> list[pygame.Rect]:
    """One rectangle per lane, left to right, filling `rect` exactly.

    Proportional to lane width, with a floor so a bike lane in a wide road is
    still visible. The floor is why the rectangles are laid out cumulatively
    rather than each from its own offset: rounding and the floor both have to come
    out of the *neighbours*, or the strip ends up wider than the button.
    """
    lanes = profile.lanes
    if not lanes or rect.width <= 0:
        return []

    floor = min(config.UI_SWATCH_MIN_LANE_PX, rect.width / len(lanes))
    widths = [max(rect.width * (lane.width / profile.total_width), floor) for lane in lanes]

    # Scale back so the strip fits the rect however much the floor added.
    total = sum(widths)
    widths = [w * rect.width / total for w in widths]

    rects: list[pygame.Rect] = []
    edge = float(rect.left)
    for i, width in enumerate(widths):
        # The last lane takes whatever integer pixels are left, so the strip ends
        # flush with the rect rather than a pixel short of it.
        right = rect.right if i == len(widths) - 1 else round(edge + width)
        rects.append(pygame.Rect(round(edge), rect.top, right - round(edge), rect.height))
        edge += width
    return rects


def draw_profile_swatch(
    surface: pygame.Surface, rect: pygame.Rect, profile: RoadProfile
) -> None:
    for lane, lane_rect in zip(profile.lanes, swatch_rects(rect, profile)):
        style = style_for(lane.type)
        pygame.draw.rect(surface, style.fill, lane_rect)
        if style.edge is not None and lane_rect.width > 2:
            pygame.draw.rect(surface, style.edge, lane_rect, 1)
    pygame.draw.rect(surface, config.Color.UI_BUTTON_EDGE, rect, 1)
