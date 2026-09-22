"""What a tool offers the user to take hold of, as data.

A handle is a *point you can grab*. Two families produce them - lane handles at
a node or along a road (`road/lane_handle.py`) and shape handles along a road
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

from collections.abc import Iterable
from dataclasses import dataclass
from enum import Enum

from ..geometry import Vec2
from ..road.lane_handle import LaneHandle, LaneHandleKind, node_lane_handles
from ..road.network import RoadNetwork


class HandleKind(Enum):
    LANE = "lane"
    """A lane's own centreline where it meets a node, or at a station along a road."""
    EDGE = "edge"
    """A boundary between two lanes, or a kerb, at the same places."""
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


_LANE_KIND = {
    LaneHandleKind.LANE: HandleKind.LANE,
    LaneHandleKind.EDGE: HandleKind.EDGE,
}


def lane_preview_handles(
    handles: Iterable[LaneHandle], active: LaneHandle | None = None
) -> list[PreviewHandle]:
    """Lane and edge handles as preview data, with the live one marked.

    One helper rather than one per tool: a lane handle looks the same whoever
    is offering it, and the only thing a tool decides is *which* set to offer
    and which handle is currently live. `active` is compared by what it names -
    segment, kind, index - not by identity, because the handle a tool is
    holding was read from an earlier rebuild of the network and is a different
    object to the one this call derives.
    """
    return [
        PreviewHandle(
            handle.position,
            _LANE_KIND[handle.kind],
            active is not None
            and handle.kind is active.kind
            and handle.index == active.index
            and handle.segment_id == active.segment_id,
        )
        for handle in handles
    ]


def node_preview_handles(
    network: RoadNetwork, node_id: int, active: LaneHandle | None = None
) -> list[PreviewHandle]:
    """Every lane and edge handle at a node, as preview data."""
    return lane_preview_handles(node_lane_handles(network, node_id), active)
