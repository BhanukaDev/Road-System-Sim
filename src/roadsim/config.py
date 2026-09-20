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

JUNCTION_MAX_TRIM_FACTOR = 3.0
"""Cap on how far a junction may push an arm back, in multiples of the widest
arm's half-width. Two arms meeting at a shallow angle have kerbs that cross
almost at infinity, so the raw intersection is unbounded; without this, dragging
a node to a shallow angle inflates the junction until it eats its own roads.
M3's corner fillets replace the straight-ray intersection and this cap with it."""

MIN_CARRIAGEWAY = 1.0
"""Metres. Below this a segment is all junction and has no road left; it is
flagged `is_too_short` and drawn as an error rather than trimmed to nothing."""

SNAP_NODE_PX = 16.0
"""Snap radii are in *pixels*, converted through `camera.zoom`. A snap that gets
harder to hit as you zoom out is a snap that is broken."""
SNAP_SEGMENT_PX = 12.0
SNAP_GRID_PX = 9.0
ANGLE_SNAP_DEG = 15.0
"""Held-Shift direction constraint while drawing."""

DIRECTION_ARROW_SPACING = 18.0
"""Metres between the travel-direction arrows drawn along each traffic lane."""
DIRECTION_ARROW_LENGTH = 3.0
DIRECTION_ARROW_MIN_PX = 26.0
"""Below this on-screen lane length, arrows are skipped rather than crammed."""


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

    LANE_CAR = (58, 61, 68)
    LANE_BUS = (72, 58, 52)
    LANE_BIKE = (52, 68, 58)
    LANE_TRAM = (64, 62, 72)
    LANE_RAIL = (46, 44, 42)
    LANE_PARKING = (52, 55, 62)
    LANE_SIDEWALK = (84, 86, 92)
    LANE_MEDIAN = (60, 70, 58)
    LANE_SHOULDER = (58, 56, 50)
    LANE_EDGE = (44, 46, 52)

    JUNCTION_FILL = (52, 55, 62)
    JUNCTION_EDGE = (44, 46, 52)
    DIRECTION_ARROW = (150, 156, 168)
    SEGMENT_ERROR = (198, 72, 64)
    NODE_MARK = (226, 168, 72)
    NODE_SELECTED = (250, 214, 130)
    SELECTION = (250, 214, 130)
    PREVIEW = (240, 196, 84)
    PREVIEW_DIM = (138, 120, 70)
    SNAP_NODE = (120, 226, 160)
    SNAP_SEGMENT = (120, 190, 226)
    SNAP_GRID = (140, 146, 158)
    SNAP_ANGLE = (226, 150, 220)

    HUD_TEXT = (214, 218, 226)
    HUD_DIM = (128, 134, 144)
    HUD_BACK = (18, 19, 22)
