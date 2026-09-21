"""Drawing roads: click to place corners, or drag to sketch one freehand.

Both routes end in the same place - a list of corner points handed to
`fit_polyline` - which is the point of D1's bargain. A stroke is simplified and
filleted by `fit_freehand`; clicked corners are filleted directly. Nothing
downstream can tell which one the user did.

An end that lands on an existing road splits it first, in the same undo step, so
a T-junction is one action and one undo.

**An end that lands on a lane handle joins by that lane (D21).** Hovering a
node here publishes its lane and edge handles, and clicking one ends the road
at that node with its profile shifted so the chosen lane lines up
(`editor/lane_draw.py`). The pairing is solved at commit, not at the click:
until the stroke has a direction there is no frame to measure a lane offset
in, and the same function then answers for both ends of the finished path.

**The preview is the commit, one frame early (D22).** Every frame the tool
plans the road it would build if the user clicked now - placed corners plus
the cursor - through `plan_road`, the same function `_commit` uses. The plan
carries the command, a `Ghost` of the network with it applied, and the first
problem the ghost has: too short, too tight, crossing another road without
meeting it, a junction that will not resolve. The overlay draws the ghost
translucently and turns it red on a problem, so what the user sees before the
click is what they get after it - a Cities: Skylines ghost, not a centreline.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import pygame

from ... import config
from ...geometry import Path, Vec2, fit_freehand, fit_polyline, ray_ray
from ...road.network import RoadNetwork
from ...road.profile import RoadProfile
from ..commands import (
    AddSegment,
    Command,
    Composite,
    CreateNode,
    NodeSlot,
    SplitSegment,
)
from ..context import AngleReadout, EditorContext, ToolPreview
from ..ghost import Ghost, ghost_of
from ..guides import find_guides
from ..handle import PreviewHandle, node_preview_handles
from ..highlight import Highlight
from ..lane_draw import profile_for_lane_ends
from ..modifiers import Modifiers
from ..snapping import Snap, SnapKind
from ..tool import Tool


class DrawRoadTool(Tool):
    name = "draw"
    hint = (
        "click corners, or drag to sketch   click a lane to join by it   "
        "[Enter]/right-click commit   [Backspace] undo point   "
        "[Shift] 15 deg   [Esc] cancel"
    )

    def __init__(self) -> None:
        self.points: list[Vec2] = []
        self.start_snap: Snap | None = None
        self.stroke: list[Vec2] | None = None
        self._pressed_at: tuple[int, int] | None = None
        self._dragging = False
        self._blocked = ""
        self._hover: Snap | None = None
        """What the cursor is over right now, kept because `ctx.cursor` is the
        point a road would *end* at and a lane handle is not that point - the
        preview needs both, and re-snapping from the landing point would ask a
        different question to the one the user answered."""

    # -- lifecycle ---------------------------------------------------------

    def activate(self, ctx: EditorContext) -> None:
        self._reset()

    def deactivate(self, ctx: EditorContext) -> None:
        self._reset()

    def _reset(self) -> None:
        self.points.clear()
        self.start_snap = None
        self.stroke = None
        self._pressed_at = None
        self._dragging = False
        self._blocked = ""
        self._hover = None

    # -- input -------------------------------------------------------------

    def handle_event(self, event: pygame.event.Event, ctx: EditorContext) -> bool:
        if event.type == pygame.MOUSEMOTION:
            return self._on_motion(event, ctx)
        if event.type == pygame.MOUSEBUTTONDOWN:
            if event.button == 1:
                self._pressed_at = event.pos
                return True
            if event.button == 3:
                self._commit(ctx)
                return True
        if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            return self._on_release(event, ctx)
        if event.type == pygame.KEYDOWN:
            return self._on_key(event, ctx)
        return False

    def _on_motion(self, event: pygame.event.Event, ctx: EditorContext) -> bool:
        self._hover = self._snap(ctx, event.pos)
        ctx.cursor = self._hover.attach_position
        self._blocked = ""  # the live plan takes over from a refused commit
        if self._pressed_at is None:
            return False
        moved = _pixels_from(self._pressed_at, event.pos)
        if not self._dragging and moved > config.DRAG_THRESHOLD_PX:
            # Turned out to be a sketch. The press point is the stroke's start.
            self._dragging = True
            self.stroke = [ctx.world(*self._pressed_at)]
            if not self.points:
                self.start_snap = self._snap(ctx, self._pressed_at)
                self.stroke[0] = self.start_snap.attach_position
        if self._dragging and self.stroke is not None:
            self.stroke.append(ctx.world(*event.pos))
        return True

    def _on_release(self, event: pygame.event.Event, ctx: EditorContext) -> bool:
        if self._dragging:
            self._finish_stroke(ctx, event.pos)
        else:
            self._place_point(ctx, event.pos)
        self._pressed_at = None
        self._dragging = False
        return True

    def _on_key(self, event: pygame.event.Event, ctx: EditorContext) -> bool:
        if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
            self._commit(ctx)
            return True
        if event.key == pygame.K_BACKSPACE:
            if self.points:
                self.points.pop()
                if not self.points:
                    self.start_snap = None
            return True
        if event.key == pygame.K_ESCAPE and (self.points or self.stroke):
            self._reset()
            ctx.status = "draw cancelled"
            return True  # swallow it, so the app does not quit mid-road
        return False

    # -- building the road -------------------------------------------------

    def _place_point(self, ctx: EditorContext, pos: tuple[int, int]) -> None:
        snap = self._snap(ctx, pos)
        # A click is also a hover: the preview must plan from where the point
        # went down, not from wherever the last motion event left the cursor.
        self._hover = snap
        ctx.cursor = snap.attach_position
        if not self.points:
            self.start_snap = snap
        # `attach_position`, not `position`: a lane handle is aimed at, but the
        # road ends at its node - the lane is honoured by the datum (D21).
        self.points.append(snap.attach_position)

    def _finish_stroke(self, ctx: EditorContext, pos: tuple[int, int]) -> None:
        """A freehand stroke is a whole road on its own - commit it at once."""
        if self.stroke is None or len(self.stroke) < 2:
            self.stroke = None
            return
        end_snap = self._snap(ctx, pos)
        self.stroke[-1] = end_snap.attach_position
        try:
            path = fit_freehand(self.stroke, config.DEFAULT_CORNER_RADIUS)
        except ValueError:
            self._reset()
            return
        self.stroke = None
        self.points = _corner_points(path, self.stroke_start(), end_snap.attach_position)
        self._commit(ctx, end_snap)

    def stroke_start(self) -> Vec2:
        return self.start_snap.attach_position if self.start_snap else Vec2(0.0, 0.0)

    def _commit(self, ctx: EditorContext, end_snap: Snap | None = None) -> None:
        points = list(self.points)
        if len(points) < 2:
            ctx.status = "need at least two points"
            return
        if end_snap is None:
            end_snap = ctx.snapper.snap(points[-1])
            points[-1] = end_snap.attach_position

        plan = plan_road(ctx, points, self.start_snap, end_snap)
        if plan.command is None or plan.invalid:
            # Not an error to recover from - the road just cannot be built as
            # drawn, so say why and leave the points where the user put them.
            # The ghost already refused it in red; this is the same verdict.
            self._blocked = plan.reason
            ctx.status = plan.reason
            return
        ctx.apply(plan.command)
        self._reset()

    # -- preview -----------------------------------------------------------

    def preview(self, ctx: EditorContext) -> ToolPreview:
        snap = self._hover or _snap_at_cursor(ctx)
        preview = ToolPreview(
            points=list(self.points),
            profile=ctx.profile,
            snap=snap,
            guides=find_guides(ctx.network, ctx.camera, ctx.cursor),
            highlights=_highlights(snap),
        )
        preview.handles = self._lane_handles(ctx, snap)
        if not self.points and not self._dragging:
            # Nothing to ghost yet: show the road's width where it would begin.
            preview.footprint = ctx.cursor

        points = self.stroke if self._dragging else [*self.points, ctx.cursor]
        if points and len(points) >= 2:
            fit = fit_freehand if self._dragging else fit_polyline
            try:
                path = fit(list(points), config.DEFAULT_CORNER_RADIUS)
            except ValueError:
                path = None  # not yet two distinct points; nothing to show
            if path is not None:
                preview.paths.append(path)
                preview.measurement = path.length
                if not self._dragging:
                    preview.angles.extend(_corner_angles(points))
                preview.angles.extend(
                    _connection_angles(ctx.network, path, self.start_snap, snap)
                )
                corners = (
                    _corner_points(path, self.stroke_start(), snap.attach_position)
                    if self._dragging
                    else list(points)
                )
                plan = plan_road(ctx, corners, self.start_snap, snap)
                preview.ghost = plan.ghost
                if plan.invalid:
                    preview.invalid = True
                    preview.reason = plan.reason

        if self._blocked:
            # A commit was just refused: its reason outranks the live plan,
            # which is about a road that includes the cursor and may be fine.
            preview.invalid = True
            preview.reason = self._blocked
        return preview

    def hud_lines(self, ctx: EditorContext) -> list[str]:
        lines = [f"# {self.hint}", f"profile: {ctx.profile.name}"]
        if self.points:
            lines.append(f"{len(self.points)} point(s) placed")
        if self._blocked:
            lines.append(self._blocked)
        return lines

    def _lane_handles(
        self, ctx: EditorContext, snap: Snap | None
    ) -> list[PreviewHandle]:
        """Every lane handle of the node the cursor is near, with the one being
        aimed at marked. Offered while drawing and not while moving (D21),
        because here picking one is the whole point of the click."""
        if snap is not None and snap.kind is SnapKind.LANE:
            handle = snap.lane_handle
            return node_preview_handles(ctx.network, handle.node_id, handle)
        near = ctx.snapper.nearest_node(ctx.cursor)
        if near is None:
            return []
        return node_preview_handles(ctx.network, near.node_id)

    # -- helpers -----------------------------------------------------------

    def _snap(self, ctx: EditorContext, pos: tuple[int, int]) -> Snap:
        return self._snap_world(ctx, ctx.world(*pos))

    def _snap_world(self, ctx: EditorContext, point: Vec2) -> Snap:
        """A lane handle beats everything else, the way a node already beats a
        segment: it is the most specific thing under the cursor, and it is the
        only one of them that says *which part* of a road was meant."""
        lane = ctx.snapper.nearest_lane_handle(point)
        if lane is not None:
            return lane
        mods = Modifiers.current()
        return ctx.snapper.snap(
            point,
            from_point=self.points[-1] if self.points else None,
            constrain_angle=mods.shift,
        )


def build_road_command(
    ctx: EditorContext,
    points: list[Vec2],
    start: Snap | None,
    end: Snap | None,
) -> Command | str:
    """One undo step for the whole road, splits included.

    Returns the command, or a message explaining why there is no road to build.
    Kept a free function so a test can exercise it without a mouse.
    """
    if _same_node(start, end):
        if _loop_too_short(points):
            return "road is too short"
        return _loop_command(ctx, points, start.attach_node_id)
    if points[0].distance_to(points[-1]) < config.MIN_ROAD_LENGTH:
        return "road is too short"

    start_hit = start.segment_hit if start else None
    end_hit = end.segment_hit if end else None
    if start_hit and end_hit and start_hit[0] == end_hit[0]:
        # The first split destroys the segment the second one is aimed at.
        return "both ends land on the same road - draw it in two goes"

    steps: list[Command] = []
    slot_a = _endpoint(steps, points[0], start)
    slot_b = _endpoint(steps, points[-1], end)
    steps.append(AddSegment(slot_a, slot_b, points, _profile_for(ctx, points, start, end)))
    if len(steps) == 1:
        return steps[0]
    return Composite(steps, label="draw road")


@dataclass(frozen=True, slots=True)
class RoadPlan:
    """A road the tool would build, and whether it can.

    `command` is `None` when the road was refused before it could be built at
    all (too short, both ends on one road). `ghost` is the network with the
    command applied; it carries the problems only building can reveal. One
    object so a preview and a commit read the same verdict from the same place.
    """

    command: Command | None
    ghost: Ghost | None
    refused: str = ""

    @property
    def invalid(self) -> bool:
        return self.command is None or (self.ghost is not None and self.ghost.invalid)

    @property
    def reason(self) -> str:
        if self.command is None:
            return self.refused
        return self.ghost.reason if self.ghost is not None else ""


def plan_road(
    ctx: EditorContext,
    points: list[Vec2],
    start: Snap | None,
    end: Snap | None,
) -> RoadPlan:
    """Build the road's command and try it on a ghost of the network.

    Called every frame for the preview and once more for the commit, with a
    fresh command each time: a command remembers the ids it allocated, so the
    one the ghost ran is a redo waiting to happen, not a first do.
    """
    command = build_road_command(ctx, points, start, end)
    if isinstance(command, str):
        return RoadPlan(None, None, command)
    try:
        ghost = ghost_of(ctx.network, command)
    except ValueError:
        # `fit_polyline` refusing the corners - two coincident points, or a
        # stroke folded back on itself. Nothing to ghost, and nothing to build.
        return RoadPlan(None, None, "road cannot be fitted as drawn")
    return RoadPlan(command, ghost)


def _highlights(snap: Snap | None) -> list[Highlight]:
    """What the snap under the cursor would act on: the road a `SEGMENT` snap
    would split, the node a `NODE` or `LANE` snap would join. A free snap acts
    on nothing, so it lights nothing."""
    if snap is None:
        return []
    if snap.kind is SnapKind.SEGMENT:
        return [Highlight.segment(snap.segment_hit[0])]
    if snap.attach_node_id is not None:
        return [Highlight.node(snap.attach_node_id)]
    return []


def _profile_for(
    ctx: EditorContext, points: list[Vec2], start: Snap | None, end: Snap | None
) -> RoadProfile:
    """The active profile, shifted if either end was drawn onto a lane (D21).

    The shift needs the road's own end frame, so it is solved here - from the
    same `fit_polyline` the segment itself will run - rather than at the click
    that chose the lane, where the road had no direction yet. A stroke that
    cannot be fitted is not this function's problem: `AddSegment` will raise on
    it either way, and guessing a datum for a road that will not exist would
    only make the failure harder to read.
    """
    start_handle = start.lane_handle if start is not None else None
    end_handle = end.lane_handle if end is not None else None
    if start_handle is None and end_handle is None:
        return ctx.profile
    try:
        path = fit_polyline(list(points), config.DEFAULT_CORNER_RADIUS)
    except ValueError:
        return ctx.profile
    return profile_for_lane_ends(ctx.profile, path, start_handle, end_handle)


def _endpoint(steps: list[Command], point: Vec2, snap: Snap | None) -> NodeSlot:
    """Turn one end of the stroke into a node id, adding commands as needed.

    A `LANE` snap resolves to its own node: the lane it names is honoured by
    the profile's datum (`_profile_for`), never by a second node."""
    if snap is not None and snap.attach_node_id is not None:
        return NodeSlot(snap.attach_node_id)
    if snap is not None and snap.kind is SnapKind.SEGMENT:
        segment_id, s = snap.segment_hit
        split = SplitSegment(segment_id, s)
        steps.append(split)
        return split.slot
    create = CreateNode(point)
    steps.append(create)
    return create.slot


def _loop_command(ctx: EditorContext, points: list[Vec2], node_id: int) -> Composite:
    """Split a same-node closure into two open segments sharing both endpoints."""
    mid = max(1, len(points) // 2)
    split = CreateNode(points[mid])
    first = AddSegment(NodeSlot(node_id), split.slot, points[: mid + 1], ctx.profile)
    second = AddSegment(split.slot, NodeSlot(node_id), points[mid:], ctx.profile)
    return Composite([split, first, second], label="draw loop")


def _loop_too_short(points: list[Vec2]) -> bool:
    if len(points) < 3:
        return True
    loop = points[:-1] if points[0].distance_to(points[-1]) <= 1e-9 else points
    try:
        return (
            fit_polyline(loop, config.DEFAULT_CORNER_RADIUS).length
            < config.MIN_ROAD_LENGTH
        )
    except ValueError:
        return True


def _same_node(a: Snap | None, b: Snap | None) -> bool:
    """Both ends on the same node - a loop. A lane handle counts, because it
    names a node too; two different lanes of one node are still one node."""
    return (
        a is not None
        and b is not None
        and a.attach_node_id is not None
        and a.attach_node_id == b.attach_node_id
    )


def _corner_points(path: Path, start: Vec2, end: Vec2) -> list[Vec2]:
    """Recover corner points from a fitted path, so the segment stores corners.

    Control points are the authoritative state (M2 design), so a freehand road
    is stored as the corners its stroke simplified to - not as the raw stroke,
    and not as the fitted path.
    """
    points = [start]
    for piece, _ in zip(path.pieces, path.piece_starts):
        entry, exit_ = piece.start, piece.end
        # Where the entry and exit tangents cross is the corner this piece
        # filleted. A straight has no such corner and `ray_ray` says so.
        corner = ray_ray(entry.position, entry.tangent, exit_.position, exit_.tangent)
        if corner is not None and corner.distance_to(points[-1]) > 1e-6:
            points.append(corner)
    if end.distance_to(points[-1]) > 1e-6:
        points.append(end)
    return points


def _snap_at_cursor(ctx: EditorContext) -> Snap:
    """The preview's fallback when no motion has been seen yet - the same
    priority as a real hover, minus the angle constraint, which belongs to a
    live modifier key and not to a repaint."""
    return ctx.snapper.nearest_lane_handle(ctx.cursor) or ctx.snapper.snap(ctx.cursor)


def _pixels_from(a: tuple[int, int], b: tuple[int, int]) -> float:
    return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5


# -- angle readouts ----------------------------------------------------------


def _angle_between(a: Vec2, b: Vec2) -> float:
    """Unsigned angle between two directions, degrees in [0, 180]."""
    cos = max(-1.0, min(1.0, a.normalized().dot(b.normalized())))
    return math.degrees(math.acos(cos))


def _arms_at_snap(network: RoadNetwork, snap: Snap) -> list[Vec2]:
    """Directions the existing road(s) at a snap point head away from it.

    A node may carry several arms (an existing junction); a mid-segment snap
    has exactly two, one each way along that one road.
    """
    if snap.attach_node_id is not None:
        node = network.nodes.get(snap.attach_node_id)
        if node is None:
            return []
        arms = []
        for segment_id in node.segments:
            segment = network.segments.get(segment_id)
            if segment is not None:
                arms.append(segment.outgoing_dir(segment.is_at_a(node.id)))
        return arms
    if snap.kind is SnapKind.SEGMENT:
        segment_id, s = snap.segment_hit
        segment = network.segments.get(segment_id)
        if segment is None:
            return []
        tangent = segment.path.sample(s).tangent
        return [tangent, -tangent]
    return []


def _connection_angle(new_dir: Vec2, arms: list[Vec2]) -> float | None:
    """How far the new road deviates from continuing straight along the
    nearest existing arm - 0 merges smoothly, 90 is a perpendicular T."""
    if not arms or new_dir.length_sq < 1e-12:
        return None
    return min(_angle_between(new_dir, arm) for arm in arms)


def _connection_angles(
    network: RoadNetwork, path: Path, start: Snap | None, end: Snap | None
) -> list[AngleReadout]:
    """Angle readouts where the previewed road meets existing geometry.

    A free (grid/angle-constrained) end is not a connection, so it gets none.
    """
    out: list[AngleReadout] = []
    if start is not None and not start.is_free:
        angle = _connection_angle(path.start.tangent, _arms_at_snap(network, start))
        if angle is not None:
            out.append(AngleReadout(path.start.position, angle))
    if end is not None and not end.is_free:
        angle = _connection_angle(-path.end.tangent, _arms_at_snap(network, end))
        if angle is not None:
            out.append(AngleReadout(path.end.position, angle))
    return out


def _corner_angles(points: list[Vec2]) -> list[AngleReadout]:
    """Turn angle at each interior corner of a clicked (not freehand) road."""
    out = []
    for i in range(1, len(points) - 1):
        incoming = points[i] - points[i - 1]
        outgoing = points[i + 1] - points[i]
        if incoming.length_sq < 1e-9 or outgoing.length_sq < 1e-9:
            continue
        out.append(AngleReadout(points[i], _angle_between(incoming, outgoing)))
    return out
