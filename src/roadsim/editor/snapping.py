"""Deciding what the cursor is actually pointing at.

Every radius here is in **pixels**, converted to metres through `camera.zoom`.
That is deliberate: a snap expressed in metres gets harder to hit the further
you zoom out, which reads to the user as the editor breaking.

Priority runs from most specific to least - an existing node beats a point on a
road, which beats a direction constraint, which beats the bare grid. The first
two carry a payload the tool acts on; the last two are just a position.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from typing import Any

from .. import config
from ..geometry import Vec2
from ..render.camera import Camera
from ..road.network import RoadNetwork


class SnapKind(Enum):
    NODE = "node"
    """Connect to an existing node. Payload: node id."""
    SEGMENT = "segment"
    """Split there and connect. Payload: (segment id, arc length)."""
    ANGLE = "angle"
    """Constrained to a fixed angle from the previous point."""
    GRID = "grid"
    """A free point, pulled onto the grid when it is close enough to one."""


@dataclass(frozen=True, slots=True)
class Snap:
    kind: SnapKind
    position: Vec2
    payload: Any = None

    @property
    def node_id(self) -> int | None:
        return self.payload if self.kind is SnapKind.NODE else None

    @property
    def segment_hit(self) -> tuple[int, float] | None:
        return self.payload if self.kind is SnapKind.SEGMENT else None

    @property
    def is_free(self) -> bool:
        """True when nothing in the network claimed this point."""
        return self.kind in (SnapKind.GRID, SnapKind.ANGLE)


class Snapper:
    def __init__(self, network: RoadNetwork, camera: Camera) -> None:
        self.network = network
        self.camera = camera

    def snap(
        self,
        point: Vec2,
        from_point: Vec2 | None = None,
        constrain_angle: bool = False,
        ignore_nodes: frozenset[int] = frozenset(),
        ignore_segments: frozenset[int] = frozenset(),
    ) -> Snap:
        node = self.nearest_node(point, ignore_nodes)
        if node is not None:
            return node
        segment = self.nearest_segment(point, ignore_segments)
        if segment is not None:
            return segment
        if constrain_angle and from_point is not None:
            return Snap(SnapKind.ANGLE, _constrain(from_point, point))
        return Snap(SnapKind.GRID, self.to_grid(point))

    # -- the individual candidates ----------------------------------------

    def nearest_node(
        self, point: Vec2, ignore: frozenset[int] = frozenset()
    ) -> Snap | None:
        reach = self.world_radius(config.SNAP_NODE_PX)
        best, best_d = None, reach
        for node in self.network.nodes.values():
            if node.id in ignore:
                continue
            d = node.position.distance_to(point)
            if d <= best_d:
                best, best_d = node, d
        if best is None:
            return None
        return Snap(SnapKind.NODE, best.position, best.id)

    def nearest_segment(
        self, point: Vec2, ignore: frozenset[int] = frozenset()
    ) -> Snap | None:
        reach = self.world_radius(config.SNAP_SEGMENT_PX)
        best: Snap | None = None
        best_d = reach
        for segment in self.network.segments.values():
            if segment.id in ignore:
                continue
            s = segment.path.project(point)
            position = segment.path.sample(s).position
            d = position.distance_to(point)
            if d <= best_d:
                best, best_d = Snap(SnapKind.SEGMENT, position, (segment.id, s)), d
        return best

    def to_grid(self, point: Vec2) -> Vec2:
        """Pull onto the grid only when the grid is within reach on screen.

        Otherwise a zoomed-out click would jump tens of metres, which is the
        opposite of helpful.
        """
        reach = self.world_radius(config.SNAP_GRID_PX)
        spacing = config.GRID_SPACING
        snapped = Vec2(
            round(point.x / spacing) * spacing, round(point.y / spacing) * spacing
        )
        return snapped if snapped.distance_to(point) <= reach else point

    def world_radius(self, pixels: float) -> float:
        return pixels / self.camera.zoom


def _constrain(origin: Vec2, point: Vec2) -> Vec2:
    """Hold the direction to a fixed angular step, keeping the distance drawn."""
    delta = point - origin
    if delta.length_sq < 1e-12:
        return point
    step = math.radians(config.ANGLE_SNAP_DEG)
    angle = round(delta.angle / step) * step
    return origin + Vec2.from_angle(angle, delta.length)
