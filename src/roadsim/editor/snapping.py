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
    `beside`), because "alongside" has no meaning without a width."""
    SEGMENT = "segment"
    """Split there and connect. Payload: (segment id, arc length).

    Found within a few pixels of the centreline, or - when the caller asks
    for `over_body` - anywhere over the carriageway (D25): a road drawn onto
    another attaches at the centreline station under the cursor, and *where*
    across the road the cursor was decides how the two arrange
    (`editor/lane_draw.py`)."""
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
        return self.payload if self.kind is SnapKind.SEGMENT else None

    @property
    def anchor(self) -> Anchor | None:
        return self.payload if self.kind is SnapKind.ANCHOR else None

    @property
    def beside(self) -> Beside | None:
        return self.payload if self.kind is SnapKind.BESIDE else None

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
        over_body: bool = False,
    ) -> Snap:
        """`beside` names the cross-section(s) being placed at `point`, so a
        `BESIDE` snap can put their kerb a verge from a neighbouring road's.
        Empty means the caller is placing a bare point and that snap is
        skipped. `over_body` widens the road snap from the centreline to the
        whole carriageway - what a tool that *attaches* to a road wants, and
        what a tool that merely places a point near one does not."""
        node = self.nearest_node(point, ignore_nodes)
        if node is not None:
            return node
        anchor = self.nearest_anchor(point, ignore_nodes, ignore_segments)
        if anchor is not None:
            return anchor
        flush = self.nearest_beside(point, beside, ignore_segments)
        if flush is not None:
            return flush
        find = self.over_segment if over_body else self.nearest_segment
        segment = find(point, ignore_segments)
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

    def over_segment(
        self, point: Vec2, ignore: frozenset[int] = frozenset()
    ) -> Snap | None:
        """The road whose carriageway `point` is over, as a `SEGMENT` snap at
        the station it projects to - what hovering, picking and attaching mean
        by "the road" (D24, D25). `nearest_segment` is the centreline within a
        few pixels; this is the asphalt, plus the same few pixels outside its
        kerbs, and the narrowest road wins where two overlap because it is
        the one you could not have meant to miss."""
        slack = self.world_radius(config.SNAP_SEGMENT_PX)
        best: Snap | None = None
        best_width = float("inf")
        for segment in self.network.segments.values():
            if segment.id in ignore:
                continue
            path = segment.path
            frame = path.sample(path.project(point))
            delta = point - frame.position
            if abs(delta.dot(frame.tangent)) > slack:
                continue
            lateral = delta.dot(frame.normal)
            profile = segment.profile
            if not (-profile.extent_right - slack <= lateral <= profile.extent_left + slack):
                continue
            if profile.total_width < best_width:
                best_width = profile.total_width
                best = Snap(SnapKind.SEGMENT, frame.position, (segment.id, frame.s))
        if best is not None:
            # The last metre of a road is its node: a split there would leave
            # a stub with no road in it, and the node is what was meant.
            segment = self.network.segments[best.segment_hit[0]]
            s = best.segment_hit[1]
            if s <= config.MIN_ROAD_LENGTH:
                node = self.network.nodes[segment.node_a]
                return Snap(SnapKind.NODE, node.position, node.id)
            if s >= segment.path.length - config.MIN_ROAD_LENGTH:
                node = self.network.nodes[segment.node_b]
                return Snap(SnapKind.NODE, node.position, node.id)
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
