"""Tunables and palette. One place to poke when something looks wrong."""

from __future__ import annotations

WINDOW_SIZE = (1440, 900)
WINDOW_TITLE = "Road System Sim"
TARGET_FPS = 60

# World units are metres throughout.
DEFAULT_ZOOM = 8.0
"""Pixels per metre."""
MIN_ZOOM = 0.5
MAX_ZOOM = 120.0
ZOOM_STEP = 1.15

GRID_SPACING = 10.0
"""Metres between minor grid lines."""
GRID_MAJOR_EVERY = 10

FLATTEN_TOLERANCE_PX = 0.35
"""Max screen-space deviation when flattening curves. Drives adaptive sampling."""

DEFAULT_CORNER_RADIUS = 12.0
"""Metres. The fillet radius the draw tool asks for at each corner."""


class Color:
    BACKGROUND = (28, 30, 34)
    GRID_MINOR = (40, 43, 48)
    GRID_MAJOR = (54, 58, 64)
    AXIS_X = (92, 58, 58)
    AXIS_Y = (58, 92, 62)

    CENTERLINE = (240, 196, 84)
    RIBBON_FILL = (66, 70, 78)
    RIBBON_EDGE = (110, 116, 126)
    NORMAL_TICK = (92, 152, 220)
    STATION_TICK = (226, 226, 230)
    ARC_CENTER = (200, 96, 180)

    HUD_TEXT = (214, 218, 226)
    HUD_DIM = (128, 134, 144)
    HUD_BACK = (18, 19, 22)
