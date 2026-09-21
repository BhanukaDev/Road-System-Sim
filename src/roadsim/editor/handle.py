"""What a tool offers the user to take hold of, as data.

A handle is a *point you can grab*. Two families produce them - lane handles at
a node (`road/lane_handle.py`) and shape handles along a road
(`road/shape_handle.py`) - and both arrive here before they reach the screen,
so `editor/overlay.py` draws one loop over one list rather than learning where
each family came from.

`ToolPreview.points` already exists and stays as it is: it is an identity-less
`list[Vec2]` that `DrawRoadTool` relies on for "the corners I have clicked so
far". A handle carries a *kind*, which is what decides how it is drawn and what
dragging it will do, so it is a sibling field rather than an overload - the same
way `guides` was added.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from ..geometry import Vec2


class HandleKind(Enum):
    LANE = "lane"
    """A lane's own centreline where it meets a node."""
    EDGE = "edge"
    """A boundary between two lanes, or a kerb, where it meets a node."""
    CONTROL = "control"
    """An authoritative interior control point of a road."""
    ARC_MID = "arc_mid"
    """The belly of a fillet - a second grip on the control point that made it."""
    ARC_END = "arc_end"
    """Where a fillet leaves or rejoins its straight. Drives the corner radius."""
    STRAIGHT_MID = "straight_mid"
    """Halfway along a straight. Dragging it inserts a control point there."""


@dataclass(frozen=True, slots=True)
class PreviewHandle:
    position: Vec2
    kind: HandleKind
    active: bool = False
    """The one being dragged, or the one the cursor is over."""
