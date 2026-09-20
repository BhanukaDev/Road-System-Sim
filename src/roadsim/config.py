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

PAN_KEY_SPEED_PX = 900.0
"""Keyboard and screen-edge pan speed, in *pixels* per second, converted to
metres through `camera.zoom`. Pixels rather than metres for the same reason snap
radii are (D8): a pan measured in metres crawls when you are zoomed in and flies
when you are zoomed out, which reads as two different controls."""
PAN_EDGE_PX = 24.0
"""How close to the window edge the cursor has to be to pan. 0 disables it."""

DRAG_THRESHOLD_PX = 6.0
"""Past this, a mouse press is a freehand stroke rather than a click."""
EDITOR_ZOOM = 6.0
"""Pixels per metre the editor opens at - wide enough to watch a junction form."""

MIN_ROAD_LENGTH = 1.0
"""Metres. Shorter than this and there is no road, only a mistake."""
MIN_LANE_CLEARANCE = 0.25
"""Metres of turning radius that must survive at a curve's innermost lane edge.

An edge `d` inside an arc of radius `r` has radius `r - d`, so once `d` reaches
`r` the edge folds through the arc centre: the exact offset raises
`DegenerateOffsetError` and the sampled ribbon renders inside out, as holes and
bowties. This is the margin that keeps the fold out of reach."""

# -- interface -------------------------------------------------------------

UI_FONT_SIZE = 15
UI_FONT_SMALL = 12
UI_PADDING = 8.0
"""Inside a panel, between its edge and its contents."""
UI_GAP = 6.0
"""Between neighbouring widgets in a bar."""
UI_RADIUS = 4
"""Corner rounding on buttons and panels, in pixels."""
UI_BAR_HEIGHT = 64.0
"""The bottom road bar. Tall enough for a cross-section swatch and a name."""
UI_ROW_HEIGHT = 30.0
"""A row of plain text buttons - the mode and tool rows."""
UI_BUTTON_WIDTH = 132.0
UI_ROW_BUTTON_WIDTH = 96.0
UI_SWATCH_HEIGHT = 16.0
"""Height of a profile's cross-section swatch inside its button."""
UI_SWATCH_MIN_LANE_PX = 2.0
"""A lane narrower than this on screen is still drawn this wide, so a bike lane
does not vanish from the swatch it is meant to explain."""


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

    UI_PANEL = (22, 24, 28)
    UI_PANEL_EDGE = (46, 50, 58)
    UI_BUTTON = (38, 41, 48)
    UI_BUTTON_HOVER = (52, 57, 66)
    UI_BUTTON_ACTIVE = (78, 104, 142)
    UI_BUTTON_EDGE = (62, 68, 78)
    UI_TEXT = (222, 226, 234)
    UI_TEXT_DIM = (136, 142, 154)
    UI_TEXT_ACTIVE = (240, 246, 255)
    UI_ACCENT = (120, 170, 236)
