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

DRIVE_ON_LEFT = True
"""Which side traffic keeps to. Handedness is a property of the *cross-section*,
not of any geometry: it decides which side of a two-way road each travel
direction sits on, so `presets.py` is its only consumer - it reverses a preset's
lane order, and nothing else in the codebase asks.

Deliberately not consulted by `turn_arrows.py`: "you turn left from the leftmost
lane of your own direction group, right from the rightmost" is true under both
conventions. What changes is which of those edges is the kerb and which is the
centreline, and the reversed lane order already says that.

Not stored in a save file, and it does not need to be: `serialization/schema.py`
writes every `LaneSpec` in full, so a network keeps the handedness it was built
with even if this flag later flips."""

GRID_SPACING = 10.0
"""Metres between minor grid lines."""
GRID_MAJOR_EVERY = 10

FLATTEN_TOLERANCE_PX = 0.35
"""Max screen-space deviation when flattening curves. Drives adaptive sampling."""

DEFAULT_CORNER_RADIUS = 12.0
"""Metres. The fillet radius the draw tool asks for at each corner."""

JUNCTION_MAX_TRIM_FACTOR = 3.0
"""Floor on an arm's trim budget, in multiples of the widest arm's half-width.

This used to be the whole cap, and as a cap it was the bug behind overlapping
Y junctions: it has no angle term, so two arms meeting at 10 degrees stopped
~16 m from the node while their kerbs did not actually separate for ~60 m, and
the two carriageways were drawn through each other. It survives as the *floor*
of `_trim_budget`, which is what it was always good at - keeping a short stub's
junction from being measured against nothing at all."""

JUNCTION_MAX_TRIM_FRACTION = 0.45
"""The rest of an arm's trim budget: a fraction of that arm's *own* length.

A shallow merge is genuinely long - a real ramp gore runs for tens of metres -
so the budget has to be able to grow with the angle. Tying it to the road's own
length is what lets it: a long ramp can give 90 m to a gore, while a short stub
still cannot be swallowed by its own junction. An arm that needs more than this
is not trimmed to fit and overlapped anyway; the junction is flagged
`is_degenerate` and drawn loudly instead."""

GORE_ANGLE_DEG = 30.0
"""Below this angle between two arms, the corner between them is a gore nose
rather than an ordinary junction corner - a merge, not a turn."""

GORE_NOSE_RADIUS = 0.6
"""Metres. The kerb radius at the nose of a gore.

`JUNCTION_CORNER_RADIUS` is wrong here and was the second half of the shallow-Y
bug: at a near-straight-through corner `corner_fillet` needs a tangent length of
`radius * tan(phi / 2)`, which at 6 m and 170 degrees is ~69 m of kerb. Clamped
by the room available, the fitted radius collapsed below `MIN_RADIUS` and the
fillet came back `None` - leaving a flat cut across the wedge and a pavement
band stretched over both carriageways. A real gore nose is a tight kerb, and at
that radius the tangent is a few metres and the arc survives."""

JUNCTION_CORNER_RADIUS = 6.0
"""Metres. Default fillet radius rounding a junction corner, before a user's
corner-handle pull or the room either arm has to give clamps it down."""

MIN_CARRIAGEWAY = 1.0
"""Metres. Below this a segment is all junction and has no road left; it is
flagged `is_too_short` and drawn as an error rather than trimmed to nothing."""

SNAP_NODE_PX = 16.0
"""Snap radii are in *pixels*, converted through `camera.zoom`. A snap that gets
harder to hit as you zoom out is a snap that is broken."""
SNAP_SEGMENT_PX = 12.0
SNAP_ANCHOR_PX = 10.0
"""Reach of a lane anchor - deliberately tighter than a plain segment snap, so
it only wins when the cursor is genuinely lined up with that lane."""
SNAP_GRID_PX = 9.0
ANGLE_SNAP_DEG = 15.0
"""Held-Shift direction constraint while drawing."""
ALIGNMENT_GUIDE_PX = 6.0
"""How close, on screen, a point must sit to a node's x or y, or to an existing
straight arm's own line, before a guide is drawn for it. Tight on purpose - a
guide is a hint the point already lines up, not an invitation to snap."""

DIRECTION_ARROW_SPACING = 18.0
"""Metres between the travel-direction arrows drawn along each traffic lane."""
DIRECTION_ARROW_LENGTH = 3.0
DIRECTION_ARROW_MIN_PX = 26.0
"""Below this on-screen lane length, arrows are skipped rather than crammed."""

STOP_LINE_WIDTH_PX = 3.0
"""Thickness of a terminal cap's stop line, in screen pixels."""

MARKING_WIDTH_PX = 2.0
"""Thickness of a lane marking line, in screen pixels."""
MARKING_DASH_LENGTH = 3.0
"""Metres of paint in one dash of a lane divider."""
MARKING_GAP_LENGTH = 5.0
"""Metres of gap between dashes."""
MARKING_MIN_PX = 20.0
"""Below this on-screen carriageway length, markings are skipped rather than
crammed - the same reasoning as `DIRECTION_ARROW_MIN_PX`."""

CROSSWALK_DEPTH = 3.0
"""Metres a crosswalk's zebra stripes run along the road, right at a real
junction's mouth."""
CROSSWALK_STRIPE_WIDTH = 0.5
CROSSWALK_STRIPE_GAP = 0.5
CROSSWALK_STOP_SETBACK = 1.2
"""Metres between the stop line and the crosswalk it serves."""
STOP_LINE_THICKNESS = 0.4
"""Metres a stop line or crosswalk stripe runs, world-space (unlike a cap's
pixel-space `STOP_LINE_WIDTH_PX` - this one has to stay a fixed width in a
zebra crossing regardless of zoom)."""

TURN_ARROW_LENGTH = 4.0
"""Metres, a turn-decal arrow - bigger than a periodic `DIRECTION_ARROW`,
since there is only one per lane rather than one every `DIRECTION_ARROW_SPACING`."""
TURN_ARROW_SETBACK = 6.0
"""Metres upstream of the stop line a turn decal sits."""
TRANSITION_ARROW_LENGTH = 9.0
"""Metres, the merge arrow painted where a lane is about to run out. Longer
than a turn decal because it is read further ahead - a driver acts on it before
reaching the taper, not at a stop line."""

TRANSITION_ARROW_LANE_FRACTION = 0.85
"""A merge arrow is a wide shape and it spans most of its lane on a real road,
so it gets more room than `TURN_ARROW_LANE_FRACTION` allows a turn decal.
Held below 1.0 all the same: a marking that touches the lane line it is telling
you to cross reads as the line being broken."""

TRANSITION_ARROW_SETBACK = 12.0
"""Metres back up its own road from the transition mouth. A merge arrow is an
instruction to change lane, so it has to arrive with room to act on it."""

TURN_ARROW_LANE_FRACTION = 0.6
"""How much of a lane's width a turn decal may take up.

Decals are scaled uniformly - squashing an arrow sideways would make it a
different marking - so a lane too narrow for the arrow at
`TURN_ARROW_LENGTH` gets a shorter one, not a thinner one."""

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
    CAP_FILL = (52, 55, 62)
    STOP_LINE = (226, 226, 230)
    MARKING_WHITE = (222, 222, 216)
    MARKING_YELLOW = (224, 178, 60)
    DIRECTION_ARROW = (150, 156, 168)
    SEGMENT_ERROR = (198, 72, 64)
    NODE_MARK = (226, 168, 72)
    NODE_SELECTED = (250, 214, 130)
    SELECTION = (250, 214, 130)
    PREVIEW = (240, 196, 84)
    PREVIEW_DIM = (138, 120, 70)
    SNAP_NODE = (120, 226, 160)
    SNAP_SEGMENT = (120, 190, 226)
    SNAP_ANCHOR = (226, 190, 120)
    SNAP_GRID = (140, 146, 158)
    SNAP_ANGLE = (226, 150, 220)
    GUIDE = (168, 120, 226)

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
