"""Alignment guides: a hint that a point lines up with something already there.

A guide is visual only - it never changes what `Snapper` accepts (that would
make `find_guides` a second, competing snap kind). It answers one question:
does this point currently line up, on x, on y, or along an existing straight
arm's own line, with a node nearby? The same three alignments a vector drawing
tool offers, and no more (item 9).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .. import config
from ..geometry import Vec2
from ..render.camera import Camera
from ..road.network import RoadNetwork


class GuideKind(Enum):
    HORIZONTAL = "horizontal"
    VERTICAL = "vertical"
    EXTENSION = "extension"
    """Colinear with an arm already leaving the anchor node."""


@dataclass(frozen=True, slots=True)
class Guide:
    kind: GuideKind
    anchor: Vec2
    """The existing point the alignment is measured from."""
    point: Vec2
    """Where the alignment was found - the overlay draws anchor -> point."""


def find_guides(network: RoadNetwork, camera: Camera, point: Vec2) -> list[Guide]:
    """Guides `point` currently sits on, worth drawing this frame.

    The reach is in *pixels*, converted through `camera.zoom` - the same reason
    `Snapper.world_radius` is (D8): a guide that gets harder to trigger as you
    zoom out would read as the editor forgetting the alignment existed.
    """
    reach = config.ALIGNMENT_GUIDE_PX / camera.zoom
    guides: list[Guide] = []
    for node in network.nodes.values():
        delta = point - node.position
        if abs(delta.x) <= reach:
            guides.append(Guide(GuideKind.VERTICAL, node.position, point))
        if abs(delta.y) <= reach:
            guides.append(Guide(GuideKind.HORIZONTAL, node.position, point))
        guides.extend(_extension_guides(network, node, point, reach))
    return guides


def _extension_guides(
    network: RoadNetwork, node, point: Vec2, reach: float
) -> list[Guide]:
    """`point` continuing an arm already leaving `node` in a straight line."""
    to_point = point - node.position
    if to_point.length_sq < 1e-9:
        return []
    out: list[Guide] = []
    for segment_id in node.segments:
        segment = network.segments.get(segment_id)
        if segment is None:
            continue
        direction = segment.outgoing_dir(segment.is_at_a(node.id))
        along = to_point.dot(direction)
        if along <= 0.0:
            continue  # behind the arm, not an extension of it
        lateral = abs(to_point.cross(direction))
        if lateral <= reach:
            out.append(Guide(GuideKind.EXTENSION, node.position, point))
    return out
