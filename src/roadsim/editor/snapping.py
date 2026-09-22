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
from ..road.anchor import Anchor, node_anchors
from ..road.lane_handle import LaneHandle, node_lane_handles, segment_lane_handles
from ..road.network import RoadNetwork
from ..road.profile import RoadProfile


class SnapKind(Enum):
    NODE = "node"
    """Connect to an existing node. Payload: node id."""
    ANCHOR = "anchor"
    """Aligned with one lane of a nearby road. Payload: the `Anchor`.

    An alignment aid, not a connection (D5) - the point it offers is a free
    one, same as `GRID` or `ANGLE`; only its *position* comes from the network.
    """
    BESIDE = "beside"
    """Alongside a nearby road: the point is placed so the snapping road's
    own kerb runs `config.BESIDE_GAP` from that road's kerb, and slides along
    it. Payload: the `Beside`.

    An alignment aid like `ANCHOR`, and a free point for the same reason. It is
    what makes two roads run parallel - a ramp beside its motorway, a service
    road beside an avenue - without the user reading widths off the screen
    (D23). Only offered when the caller says what is being placed (`snap()`'s
    `beside`), because "flush" has no meaning without a width."""
    LANE = "lane"
    """A lane or lane-edge handle, at a node or along a road. Payload: the
    `LaneHandle`.

    A real connection, not an aid: a road drawn onto one ends at that handle's
    node - splitting the road there first when the handle is along it - and is
    shifted so the chosen lane lines up (`editor/lane_draw.py`, D21, D23).
    Asked for explicitly by the tools that can act on one, never through
    `snap()` - offering it to every tool would mean each of them deciding what
    a lane means to it, which is the branch a registry exists to avoid."""
    SEGMENT = "segment"
    """Split there and connect. Payload: (segment id, arc length)."""
    ANGLE = "angle"
    """Constrained to a fixed angle from the previous point."""
    GRID = "grid"
    """A free point, pulled onto the grid when it is close enough to one."""


@dataclass(frozen=True, slots=True)
class Beside:
    """What a `BESIDE` snap lined up with: one kerb of one road."""

    segment_id: int
    s: float
    """Station along that road the point sits beside."""
    tangent: Vec2
    """That road's direction there - the line the snapped point slides along."""
    kerb: Vec2
    """The point on that road's kerb the snapping road's kerb was put against."""


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
        """The road a road drawn to this snap would split, and where. A `LANE`
        snap along a road names one as surely as a `SEGMENT` snap does."""
        if self.kind is SnapKind.SEGMENT:
            return self.payload
        if self.kind is SnapKind.LANE and self.payload.node_id is None:
            return (self.payload.segment_id, self.payload.station)
        return None

    @property
    def anchor(self) -> Anchor | None:
        return self.payload if self.kind is SnapKind.ANCHOR else None

    @property
    def beside(self) -> Beside | None:
        return self.payload if self.kind is SnapKind.BESIDE else None

    @property
    def lane_handle(self) -> LaneHandle | None:
        return self.payload if self.kind is SnapKind.LANE else None

    @property
    def attach_node_id(self) -> int | None:
        """The node a road drawn to this snap should end at, if any. A `LANE`
        snap at a node names one as surely as a `NODE` snap does - it is a node
        plus the lane that was pointed at. One along a road names none yet: the
        split will make it."""
        if self.kind is SnapKind.NODE:
            return self.payload
        if self.kind is SnapKind.LANE:
            return self.payload.node_id
        return None

    @property
    def attach_position(self) -> Vec2:
        """Where a road drawn to this snap actually ends. Everything but a
        `LANE` snap ends where it points; a lane handle ends at its *centre* -
        the node, or the split point - with the lane honoured by the profile's
        datum instead (D21)."""
        if self.kind is SnapKind.LANE:
            return self.payload.centre
        return self.position

    @property
    def is_free(self) -> bool:
        """True when nothing in the network claimed this point."""
        return self.kind in (
            SnapKind.ANCHOR,
            SnapKind.BESIDE,
            SnapKind.GRID,
            SnapKind.ANGLE,
        )


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
        beside: tuple[RoadProfile, ...] = (),
    ) -> Snap:
        """`beside` names the cross-section(s) being placed at `point`, so a
        `BESIDE` snap can put their kerb against a neighbouring road's. Empty
        means the caller is placing a bare point and that snap is skipped."""
        node = self.nearest_node(point, ignore_nodes)
        if node is not None:
            return node
        anchor = self.nearest_anchor(point, ignore_nodes, ignore_segments)
        if anchor is not None:
            return anchor
        flush = self.nearest_beside(point, beside, ignore_segments)
        if flush is not None:
            return flush
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

    def nearest_anchor(
        self,
        point: Vec2,
        ignore_nodes: frozenset[int] = frozenset(),
        ignore_segments: frozenset[int] = frozenset(),
    ) -> Snap | None:
        reach = self.world_radius(config.SNAP_ANCHOR_PX)
        best: Snap | None = None
        best_d = reach
        for node in self.network.nodes.values():
            if node.id in ignore_nodes:
                continue
            for anchor in node_anchors(self.network, node.id):
                if anchor.segment_id in ignore_segments:
                    continue
                traveled = max(0.0, (point - anchor.origin).dot(anchor.direction))
                position = anchor.point_at(traveled)
                d = position.distance_to(point)
                if d <= best_d:
                    best, best_d = Snap(SnapKind.ANCHOR, position, anchor), d
        return best

    def nearest_beside(
        self,
        point: Vec2,
        profiles: tuple[RoadProfile, ...],
        ignore_segments: frozenset[int] = frozenset(),
    ) -> Snap | None:
        """The point moved sideways so one of `profiles`' kerbs runs a verge's
        width (`config.BESIDE_GAP`) from the kerb of the road it is beside,
        keeping its station along that road.

        Only kerb-beside-kerb is offered. Any other pairing of one road's lane
        lines with another's - lane on lane, edge on edge - puts the two
        carriageways *through* each other, which is a crossing to be drawn as
        one, not an alignment to snap to. The two roads may run either way
        relative to each other, so both of a profile's kerbs are tried against
        both of the neighbour's.

        The point has to actually be beside the road: a projection that
        clamped to an end is beyond it, and extending a kerb line past a
        dead end is `Anchor`'s job.
        """
        if not profiles:
            return None
        own_kerbs = {p.extent_left for p in profiles} | {p.extent_right for p in profiles}
        reach = self.world_radius(config.SNAP_BESIDE_PX)
        best: Snap | None = None
        best_d = reach
        for segment in self.network.segments.values():
            if segment.id in ignore_segments:
                continue
            path = segment.path
            frame = path.sample(path.project(point))
            delta = point - frame.position
            if abs(delta.dot(frame.tangent)) > reach:
                continue  # past the end of the road, not beside it
            lateral = delta.dot(frame.normal)
            kerbs = (
                (segment.profile.extent_left, 1.0),
                (segment.profile.extent_right, -1.0),
            )
            for kerb_extent, side in kerbs:
                kerb = frame.position + frame.normal * (side * kerb_extent)
                for own in own_kerbs:
                    target = side * (kerb_extent + config.BESIDE_GAP + own)
                    d = abs(lateral - target)
                    if d <= best_d:
                        position = frame.position + frame.normal * target
                        hit = Beside(segment.id, frame.s, frame.tangent, kerb)
                        best, best_d = Snap(SnapKind.BESIDE, position, hit), d
        return best

    def nearest_lane_handle(
        self,
        point: Vec2,
        ignore_nodes: frozenset[int] = frozenset(),
        ignore_segments: frozenset[int] = frozenset(),
    ) -> Snap | None:
        """The nearest lane or edge handle - at a node, or along a road.

        Not part of `snap()`'s chain (see `SnapKind.LANE`); a tool calls this
        directly, the same way `nearest_node` and `nearest_anchor` already are.

        At a node the reach is `SNAP_LANE_PX`, tight, because the handles sit
        a lane apart and the node itself is the alternative. Along a road the
        whole carriageway is the target: anywhere over the body - or within
        reach outside its kerbs - picks the nearest lane line at the station
        the cursor projects to, so hovering a road always names a lane rather
        than falling through to a bare grid point between two of them. The
        node's handles keep a node's own snap reach of either end to
        themselves: two sets a few pixels apart would fight over the cursor,
        and a split that close to a node would leave a stub with no
        carriageway in it anyway.
        """
        reach = self.world_radius(config.SNAP_LANE_PX)
        best: Snap | None = None
        best_d = reach
        for node in self.network.nodes.values():
            if node.id in ignore_nodes:
                continue
            for handle in node_lane_handles(self.network, node.id):
                if handle.segment_id in ignore_segments:
                    continue
                d = handle.position.distance_to(point)
                if d <= best_d:
                    best, best_d = Snap(SnapKind.LANE, handle.position, handle), d
        if best is not None:
            return best
        end_zone = self.world_radius(config.SNAP_NODE_PX)
        best_d = float("inf")
        for segment in self.network.segments.values():
            if segment.id in ignore_segments:
                continue
            path = segment.path
            s = path.project(point)
            if s < end_zone or s > path.length - end_zone:
                continue
            frame = path.sample(s)
            delta = point - frame.position
            if abs(delta.dot(frame.tangent)) > reach:
                continue  # projection clamped to an end: not over this road
            if abs(delta.dot(frame.normal)) > segment.profile.half_width + reach:
                continue  # beside the road, not over it
            for handle in segment_lane_handles(segment, s):
                d = handle.position.distance_to(point)
                if d <= best_d:
                    best, best_d = Snap(SnapKind.LANE, handle.position, handle), d
        return best

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
