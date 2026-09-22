"""What a tool offers the user to take hold of, as data.

A handle is a *point you can grab*. Shape handles along a selected road
(`road/shape_handle.py`) arrive here before they reach the screen, so
`editor/overlay.py` draws one loop over one list and a test can assert what is
on offer with no window open.

`ToolPreview.points` already exists and stays as it is: it is an identity-less
`list[Vec2]` that `DrawRoadTool` relies on for "the corners I have clicked so
far". A handle carries a *kind*, which is what decides how it is drawn and what
dragging it will do, so it is a sibling field rather than an overload - the same
way `guides` was added.

Lane handles used to be a second family here (D21). They went with D25: which
lane a narrower road lines up with is now read off where the cursor is across
the wider road, and there is nothing for the user to take hold of.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from ..geometry import Vec2


class HandleKind(Enum):
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
