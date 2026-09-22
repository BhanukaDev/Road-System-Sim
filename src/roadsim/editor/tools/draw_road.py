"""Drawing roads: click to place corners, or drag to sketch one freehand.

Both routes end in the same place - a list of corner points handed to
`fit_polyline` - which is the point of D1's bargain. A stroke is simplified and
filleted by `fit_freehand`; clicked corners are filleted directly. Nothing
downstream can tell which one the user did.

An end that lands on an existing road splits it first, in the same undo step, so
a T-junction is one action and one undo. "Lands on" means anywhere over its
carriageway, not only within a few pixels of its centreline (D24).

**A narrower road arranges itself across a wider one by where the cursor is
(D25).** Starting a stroke on a road of a different width records an
`Attachment` - that road's centreline point and normal there. While the second
point is placed, the cursor's lateral position across the wide road picks the
arrangement: hug the near kerb, sit on the far lanes, centre. The ghost shows
it, because the ghost is the road. The second click locks it, so the rest of
the stroke can wander without moving the join. An end that finishes across a
wider road is arranged by where across it the cursor landed. Roads of equal
width have nothing to arrange and simply centre. Before a first point, the
footprint disc sits where the arranged body would be.

**A free end can run alongside another road.** With nothing under the cursor
to connect to, `Snapper.snap` is told the profile the road will be built with
- shifted, if its start was arranged - so a point near a neighbouring road is
pulled sideways until the two run parallel a verge apart, the `BESIDE` snap.
That is how the parallel run of a ramp is placed without reading widths off
the screen (D23).

**The preview is the commit, one frame early (D22).** Every frame the tool
plans the road it would build if the user clicked now - placed corners plus
the cursor - through `plan_road`, the same function `_commit` uses. The plan
carries the command, a `Ghost` of the network with it applied, and the first
problem the ghost has: too short, too tight, crossing another road without
meeting it, a junction that will not resolve. The overlay draws the ghost
translucently and turns it red on a problem, so what the user sees before the
click is what they get after it - a Cities: Skylines ghost, not a centreline.

**A long stroke is several roads (D24).** Straights long enough are cut into
pieces with a node at each cut, so a part of a long road can be selected,
deleted or moved on its own. Every cut is a straight through-joint of one
profile, so the drawing does not change.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import pygame

from ... import config
from ...geometry import LineSegment, Path, Vec2, fit_freehand, fit_polyline, ray_ray
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
from ..context import AngleReadout, EditorContext, Selection, ToolPreview
from ..ghost import Ghost, ghost_of
from ..guides import find_guides
from ..highlight import Highlight
from ..lane_draw import (
    Attachment,
    attachment_for,
    choose_arrangement,
    datum_for_arrangement,
    profile_for_ends,
    same_width,
)
from ..modifiers import Modifiers
from ..snapping import Snap, SnapKind
from ..tool import Tool


class DrawRoadTool(Tool):
    name = "draw"
    hint = (
        "click corners, or drag to sketch   on a wider road, move across it to "
        "choose the lanes   [Ctrl+click] add a node on a road   "
        "[Enter]/right-click commit   [Backspace] undo point   [Shift] 15 deg   "
        "[Esc] cancel"
    )

    def __init__(self) -> None:
        self.points: list[Vec2] = []
        self.start_snap: Snap | None = None
        self.start_attachment: Attachment | None = None
        """The wider (or narrower) road the stroke began across, if any."""
        self.arrangement: float | None = None
        """The locked start arrangement, once a second point is down."""
        self.stroke: list[Vec2] | None = None
        self._pressed_at: tuple[int, int] | None = None
        self._dragging = False
        self._blocked = ""
        self._hover: Snap | None = None
        """What the cursor is over right now."""
        self._raw: Vec2 = Vec2(0.0, 0.0)
        """The cursor's own world position - `ctx.cursor` is the snapped point,
        and an arrangement is read from where the cursor really is across the
        road, not from the centreline it snapped to."""
        self._last_click: Vec2 = Vec2(0.0, 0.0)
        """The raw position of the last placed point, for the end arrangement
        when the road is committed with the keyboard."""

    # -- lifecycle ---------------------------------------------------------

    def activate(self, ctx: EditorContext) -> None:
        self._reset()

    def deactivate(self, ctx: EditorContext) -> None:
        self._reset()

    def _reset(self) -> None:
        self.points.clear()
        self.start_snap = None
        self.start_attachment = None
        self.arrangement = None
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
        self._raw = ctx.world(*event.pos)
        self._hover = self._snap_world(ctx, self._raw)
        ctx.cursor = self._hover.position
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
                self.start_attachment = attachment_for(
                    ctx.network, self.start_snap, ctx.profile
                )
                self.stroke[0] = self.start_snap.position
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
                if len(self.points) < 2:
                    self.arrangement = None  # the second point chose it
                if not self.points:
                    self.start_snap = None
                    self.start_attachment = None
            return True
        if event.key == pygame.K_ESCAPE and (self.points or self.stroke):
            self._reset()
            ctx.status = "draw cancelled"
            return True  # swallow it, so the app does not quit mid-road
        return False

    # -- building the road -------------------------------------------------

    def _place_point(self, ctx: EditorContext, pos: tuple[int, int]) -> None:
        point = ctx.world(*pos)
        if not self.points and Modifiers.current().ctrl:
            if self.add_node_at(ctx, point):
                return
        self.place(ctx, point)

    def place(self, ctx: EditorContext, point: Vec2) -> Snap:
        """Put a corner down at the snap under `point`. Public so a test can
        drive the tool in world space with no window open."""
        snap = self._snap_world(ctx, point)
        # A click is also a hover: the preview must plan from where the point
        # went down, not from wherever the last motion event left the cursor.
        self._hover = snap
        self._raw = point
        self._last_click = point
        ctx.cursor = snap.position
        if not self.points:
            self.start_snap = snap
            self.start_attachment = attachment_for(ctx.network, snap, ctx.profile)
            self.arrangement = None
        elif len(self.points) == 1 and self.start_attachment is not None:
            # The second point locks the arrangement the cursor chose.
            self.arrangement = self.start_arrangement(ctx, point)
        self.points.append(snap.position)
        return snap

    def add_node_at(self, ctx: EditorContext, point: Vec2) -> bool:
        """Cut the road under `point` at that station - Ctrl+click before a
        first point (D24). The same `SplitSegment` a T-junction makes, without
        the road that would have made it, so the two halves are a straight
        through-joint of one profile and draw exactly as the whole did. Too
        close to either end there is no road to cut, and the status says so."""
        over = ctx.snapper.over_segment(point)
        if over is None:
            return False
        if over.segment_hit is None:
            # The last metre of a road answers as its node (`over_segment`):
            # there is already a node here to add.
            ctx.status = "too close to the end of the road to add a node"
            return True
        segment_id, s = over.segment_hit
        segment = ctx.network.segments[segment_id]
        if segment.is_transition:
            ctx.status = "a lane change cannot be cut"
            return True
        split = SplitSegment(segment_id, s)
        ctx.apply(split)
        ctx.select(Selection(node=split.new_node_id))
        return True

    def _finish_stroke(self, ctx: EditorContext, pos: tuple[int, int]) -> None:
        """A freehand stroke is a whole road on its own - commit it at once."""
        if self.stroke is None or len(self.stroke) < 2:
            self.stroke = None
            return
        raw_end = ctx.world(*pos)
        end_snap = self._snap_world(ctx, raw_end)
        self.stroke[-1] = end_snap.position
        try:
            path = fit_freehand(self.stroke, config.DEFAULT_CORNER_RADIUS)
        except ValueError:
            self._reset()
            return
        self.stroke = None
        self.points = _corner_points(path, self.stroke_start(), end_snap.position)
        # A sketch has no second click to lock the arrangement; where the hand
        # let go says which side of the road it was heading for.
        if self.start_attachment is not None:
            self.arrangement = self.start_arrangement(ctx, raw_end)
        self._last_click = raw_end
        self._commit(ctx, end_snap, raw_end)

    def stroke_start(self) -> Vec2:
        return self.start_snap.position if self.start_snap else Vec2(0.0, 0.0)

    def _commit(
        self, ctx: EditorContext, end_snap: Snap | None = None, raw_end: Vec2 | None = None
    ) -> None:
        points = list(self.points)
        if len(points) < 2:
            ctx.status = "need at least two points"
            return
        if end_snap is None:
            end_snap = self._snap_world(ctx, points[-1])
            points[-1] = end_snap.position
            raw_end = self._last_click
        assert raw_end is not None

        plan = plan_road(
            ctx,
            points,
            self.start_snap,
            end_snap,
            self.start_arrangement(ctx, raw_end),
            self.end_arrangement(ctx, end_snap, raw_end),
        )
        if plan.command is None or plan.invalid:
            # Not an error to recover from - the road just cannot be built as
            # drawn, so say why and leave the points where the user put them.
            # The ghost already refused it in red; this is the same verdict.
            self._blocked = plan.reason
            ctx.status = plan.reason
            return
        ctx.apply(plan.command)
        self._reset()

    # -- arrangements --------------------------------------------------------

    def start_arrangement(self, ctx: EditorContext, raw: Vec2) -> float | None:
        """The arrangement across the road the stroke began on: the locked one
        once a second point is down, else the one `raw` is nearest to."""
        if self.start_attachment is None:
            return None
        if self.arrangement is not None:
            return self.arrangement
        return choose_arrangement(
            self.start_attachment.profile,
            ctx.profile,
            self.start_attachment.lateral(raw),
        )

    def end_arrangement(
        self, ctx: EditorContext, end: Snap | None, raw: Vec2
    ) -> float | None:
        """The arrangement across a road the stroke ends on, from where across
        it the cursor is."""
        attachment = attachment_for(ctx.network, end, ctx.profile)
        if attachment is None:
            return None
        return choose_arrangement(attachment.profile, ctx.profile, attachment.lateral(raw))

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
        if not self.points and not self._dragging:
            # Nothing to ghost yet: show the road's width where it would begin.
            preview.footprint = self._footprint(ctx, snap)

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
                    _corner_points(path, self.stroke_start(), snap.position)
                    if self._dragging
                    else list(points)
                )
                plan = plan_road(
                    ctx,
                    corners,
                    self.start_snap,
                    snap,
                    self.start_arrangement(ctx, self._raw),
                    self.end_arrangement(ctx, snap, self._raw),
                )
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

    def _footprint(self, ctx: EditorContext, snap: Snap) -> Vec2:
        """Where the disc goes before a first point: under the cursor, or -
        across a road of another width - where the arranged body would sit,
        so the user sees the ramp beside the carriageway rather than a disc on
        the centreline it will hang off (D25)."""
        attachment = attachment_for(ctx.network, snap, ctx.profile)
        if attachment is None:
            return ctx.cursor
        c = choose_arrangement(attachment.profile, ctx.profile, attachment.lateral(self._raw))
        return attachment.target(c) if c is not None else ctx.cursor

    def hud_lines(self, ctx: EditorContext) -> list[str]:
        lines = [f"# {self.hint}", f"profile: {ctx.profile.name}"]
        if self.points:
            lines.append(f"{len(self.points)} point(s) placed")
        if self.start_attachment is not None:
            c = self.start_arrangement(ctx, self._raw)
            if c is not None:
                state = "locked" if self.arrangement is not None else "choosing"
                lines.append(
                    f"across {self.start_attachment.profile.name}: {c:+.1f} m ({state})"
                )
        if self._blocked:
            lines.append(self._blocked)
        return lines

    # -- helpers -----------------------------------------------------------

    def _snap(self, ctx: EditorContext, pos: tuple[int, int]) -> Snap:
        return self._snap_world(ctx, ctx.world(*pos))

    def _snap_world(self, ctx: EditorContext, point: Vec2) -> Snap:
        mods = Modifiers.current()
        return ctx.snapper.snap(
            point,
            from_point=self.points[-1] if self.points else None,
            constrain_angle=mods.shift,
            beside=(self._profile_if_ended_at(ctx, point),),
            over_body=True,
        )

    def _profile_if_ended_at(self, ctx: EditorContext, point: Vec2) -> RoadProfile:
        """The cross-section the road would be built with if it ended at
        `point` - the active profile, shifted if the stroke began arranged
        across another road.

        A `BESIDE` snap lays a *kerb* against a neighbour, and a road that
        started arranged has had its kerbs moved by that datum, so the
        parallel position has to be solved for the shifted profile or the run
        ends up a lane's width off. The datum depends on the start frame,
        which two or more placed points fix before the end is chosen; with one
        point placed the frame still turns with the cursor and the answer is
        the best estimate until the next click - the ghost shows the truth
        either way.
        """
        if not self.points or self.start_attachment is None:
            return ctx.profile
        c = self.start_arrangement(ctx, point)
        if c is None:
            return ctx.profile
        try:
            path = fit_polyline([*self.points, point], config.DEFAULT_CORNER_RADIUS)
        except ValueError:
            return ctx.profile
        return profile_for_ends(ctx.profile, path, (self.start_attachment, c), None)


def build_road_command(
    ctx: EditorContext,
    points: list[Vec2],
    start: Snap | None,
    end: Snap | None,
    start_c: float | None = None,
    end_c: float | None = None,
) -> Command | str:
    """One undo step for the whole road, splits and cuts included.

    `start_c` and `end_c` are the arrangements across the roads the two ends
    attach to (D25), or `None` where an end is free or the widths match.
    Returns the command, or a message explaining why there is no road to
    build. Kept a free function so a test can exercise it without a mouse.
    """
    if _same_node(start, end):
        if _loop_too_short(points):
            return "road is too short"
        return _loop_command(ctx, points, start.node_id)
    if points[0].distance_to(points[-1]) < config.MIN_ROAD_LENGTH:
        return "road is too short"

    start_hit = start.segment_hit if start else None
    end_hit = end.segment_hit if end else None
    if start_hit and end_hit and start_hit[0] == end_hit[0]:
        # The first split destroys the segment the second one is aimed at.
        return "both ends land on the same road - draw it in two goes"
    for hit in (start_hit, end_hit):
        if hit and ctx.network.segments[hit[0]].is_transition:
            return "a road cannot join inside a lane change"

    profile = ctx.profile
    try:
        path = fit_polyline(list(points), config.DEFAULT_CORNER_RADIUS)
    except ValueError:
        # `AddSegment` will raise the same way and the ghost will say so.
        steps: list[Command] = []
        slot_a = _endpoint(steps, points[0], start)
        slot_b = _endpoint(steps, points[-1], end)
        steps.append(AddSegment(slot_a, slot_b, points, profile))
        return Composite(steps, label="draw road") if len(steps) > 1 else steps[0]

    # The road is centred on its own nodes (D28). Where an end is *arranged*
    # across another road, the drawn line is that road's centreline and the
    # body sits `d` to one side of it - so the body's own centreline is the
    # drawn path offset by `d`, and that is where the road's nodes go. The
    # lateral step from the attach node to the body is taken up by a taper.
    d_start = _arranged_lateral(ctx, start, start_c, path, at_a=True)
    d_end = _arranged_lateral(ctx, end, end_c, path, at_a=False)
    # One body, one offset. A road arranged at both ends cannot sit to one
    # side of each unless it slides between them, which is a taper's job and
    # not a road's; the start's arrangement decides, as in D25.
    d_body = d_start if abs(d_start) > 1e-9 else d_end
    if abs(d_body) < config.TRANSITION_MIN_SLIDE:
        d_body = 0.0  # a road leaving square on is centred, not slid millimetres
    if abs(d_body) > 1e-9:
        shifted = path.offset(d_body)
        body_corners = _corner_points(shifted, shifted.start.position, shifted.end.position)
        try:
            body = fit_polyline(body_corners, config.DEFAULT_CORNER_RADIUS)
        except ValueError:
            return "road cannot be fitted as drawn"
    else:
        body_corners, body = list(points), path

    # A taper is owed at an end that is attached to something and does not
    # meet it centred: a width change continued from a dead end (D26), a
    # body arranged to one side of the road it joins, or a body carried past
    # the node it ends on by the arrangement at its other end.
    start_section = _taper_section(ctx, start, profile, path, leaving=True)
    end_section = _taper_section(ctx, end, profile, path, leaving=False)
    start_attached = start is not None and not start.is_free
    end_attached = end is not None and not end.is_free
    need_start = start_attached and (start_section is not None or abs(d_body) > 1e-9)
    need_end = end_attached and (end_section is not None or abs(d_body) > 1e-9)
    start_taper = end_taper = 0.0
    if need_start:
        room = _straight_room(body, at_start=True)
        if room < config.TRANSITION_MIN_LENGTH:
            return (
                "no room for the lane change before the first bend"
                if start_section is not None
                else "bends too soon after the join for the road to centre itself"
            )
        start_taper = _taper_length(start_section or profile, profile, room)
    if need_end:
        room = _straight_room(body, at_start=False)
        if room < config.TRANSITION_MIN_LENGTH:
            return (
                "no room for the lane change after the last bend"
                if end_section is not None
                else "bends too close to the join for the road to centre itself"
            )
        end_taper = _taper_length(end_section or profile, profile, room)
    if start_taper + end_taper > body.length + 1e-9:
        # Two tapers on one short straight share it. A slide is elastic - any
        # length above the minimum does - so the slides give first; a width
        # change keeps its rate, and if the road is still too short, it is.
        start_taper, end_taper = _share_length(
            start_taper, end_taper, start_section is None, end_section is None, body.length
        )
        if start_taper + end_taper > body.length + 1e-9:
            return "too short for the lane changes at both ends"
    leftover = body.length - start_taper - end_taper
    if 0.0 < leftover < config.MIN_ROAD_LENGTH and (start_taper > 0.0 or end_taper > 0.0):
        # A sliver of plain road between a taper and the end is no road at
        # all; the taper takes it.
        if start_taper > 0.0:
            start_taper += leftover
        else:
            end_taper += leftover

    steps: list[Command] = []
    slot_a = _endpoint(steps, body_corners[0], start)
    slot_b = _endpoint(steps, body_corners[-1], end)
    length = body.length
    stations: list[float] = []
    if 0.0 < start_taper < length - 1e-9:
        stations.append(start_taper)
    stations.extend(auto_node_stations(body, start_taper, length - end_taper))
    if 0.0 < end_taper < length - 1e-9 and length - end_taper > start_taper + 1e-9:
        stations.append(length - end_taper)

    # What each taper runs between, in its own A -> B direction. At the
    # attach node the section is the road being continued (a dead end) or
    # this road's own, set `d_body` to one side (a branch - the body arrives
    # there offset by exactly that); at the body end it is this road's own,
    # centred.
    start_profile = start_section or profile.with_datum(d_body)
    end_profile = end_section or profile.with_datum(d_body)

    if not stations:
        if start_taper > 0.0:
            steps.append(AddSegment(slot_a, slot_b, [points[0], body_corners[-1]], start_profile, profile_b=profile))
        elif end_taper > 0.0:
            steps.append(AddSegment(slot_a, slot_b, [body_corners[0], points[-1]], profile, profile_b=end_profile))
        else:
            steps.append(AddSegment(slot_a, slot_b, body_corners, profile))
    else:
        # A long stroke is several roads (D24): a node at every cut, each
        # piece carrying the corners that fall inside it, one profile shared -
        # except a taper piece at either end, which runs between two.
        parts = partition_corners(body_corners, body, stations)
        if start_taper > 0.0:
            parts[0][0] = points[0]  # the taper leaves from the attach node itself
        if end_taper > 0.0:
            parts[-1][-1] = points[-1]  # and arrives at it
        slots = [slot_a]
        for part in parts[:-1]:
            create = CreateNode(part[-1])
            steps.append(create)
            slots.append(create.slot)
        slots.append(slot_b)
        last = len(parts) - 1
        for i, (part, slot_from, slot_to) in enumerate(zip(parts, slots, slots[1:])):
            if i == 0 and start_taper > 0.0:
                steps.append(AddSegment(slot_from, slot_to, part, start_profile, profile_b=profile))
            elif i == last and end_taper > 0.0:
                steps.append(AddSegment(slot_from, slot_to, part, profile, profile_b=end_profile))
            else:
                steps.append(AddSegment(slot_from, slot_to, part, profile))
    if len(steps) == 1:
        return steps[0]
    return Composite(steps, label="draw road")


def _arranged_lateral(
    ctx: EditorContext, snap: Snap | None, c: float | None, path: Path, at_a: bool
) -> float:
    """How far to one side of the drawn line the body sits at this end, in
    the drawn path's own end frame - zero when the end is not arranged."""
    if c is None:
        return 0.0
    attachment = attachment_for(ctx.network, snap, ctx.profile)
    if attachment is None:
        return 0.0
    return datum_for_arrangement(path, at_a, attachment, c)


def _taper_section(
    ctx: EditorContext,
    snap: Snap | None,
    profile: RoadProfile,
    path: Path | None,
    leaving: bool,
) -> RoadProfile | None:
    """The section a taper at this end runs from or to, or `None` when no
    taper is owed there.

    A taper is owed where the stroke *continues* a road of another width from
    its dead end: two arms, one road, the new one leaving within
    `TRANSITION_MAX_KINK_DEG` of the old one's line. Anywhere else the new
    road is a branch or a turn - a junction node, a split mid-road, a dead end
    left at a sharp angle - arranged by its datum and resolved by the junction
    itself (D25); a taper there would be a short stub across a kink that the
    junction trims to nothing. The section is returned oriented along the new
    road's own A -> B, which is what a taper stores: leaving a node the
    existing road *arrived* at means reading that road forwards when its B
    end is there and mirrored when its A end is; arriving at a node the
    existing road *leaves* from is the other way round.
    """
    if snap is None or snap.node_id is None or path is None:
        return None
    node = ctx.network.nodes.get(snap.node_id)
    if node is None or node.degree != 1:
        return None
    ((existing, at_a),) = ctx.network.segments_at(node.id)
    section = existing.profile_at(at_a)
    if same_width(section, profile):
        return None
    # Does the new road carry straight on? Its direction through the node,
    # against the old road's direction through the node.
    through_new = path.start.tangent if leaving else path.end.tangent
    through_old = -existing.outgoing_dir(at_a) if leaving else existing.outgoing_dir(at_a)
    if _angle_between(through_new, through_old) > config.TRANSITION_MAX_KINK_DEG:
        return None
    if leaving:
        return section.mirrored() if at_a else section
    return section if at_a else section.mirrored()


def _share_length(
    start: float, end: float, start_elastic: bool, end_elastic: bool, length: float
) -> tuple[float, float]:
    """Fit two tapers into `length`: shrink the elastic ones (slides) down to
    `TRANSITION_MIN_LENGTH`, splitting what is left between them; a width
    change keeps the length its rate gave it."""
    minimum = config.TRANSITION_MIN_LENGTH
    fixed = (0.0 if start_elastic else start) + (0.0 if end_elastic else end)
    spare = length - fixed
    elastic = int(start_elastic) + int(end_elastic)
    if elastic == 0 or spare < minimum * elastic:
        return start, end  # nothing to give, or not enough: the caller refuses
    if start_elastic and end_elastic:
        each = spare / 2.0
        return min(start, each), min(end, each)
    if start_elastic:
        return min(start, spare), end
    return start, min(end, spare)


def _taper_length(section: RoadProfile, profile: RoadProfile, room: float) -> float:
    """How long the taper at an end is, given `room` of straight to put it on.

    A width change is visible, so it takes `TRANSITION_TAPER_RATE` metres per
    metre of change and no more. A slide - the same section, only centred
    elsewhere - is invisible, so it takes the whole straight up to
    `TRANSITION_SLIDE_LENGTH`: the arm a junction trims is the taper, and a
    shallow gore wants tens of metres of it.
    """
    change = abs(section.total_width - profile.total_width)
    if change > 1e-9:
        wanted = max(config.TRANSITION_MIN_LENGTH, config.TRANSITION_TAPER_RATE * change)
    else:
        wanted = config.TRANSITION_SLIDE_LENGTH
    return max(config.TRANSITION_MIN_LENGTH, min(wanted, room))


def _straight_room(path: Path, at_start: bool) -> float:
    """How much straight road there is before the first bend (or after the
    last) - the most a taper at that end can be, since a taper is straight."""
    piece = path.pieces[0] if at_start else path.pieces[-1]
    return piece.length if isinstance(piece, LineSegment) else 0.0


def auto_node_stations(path: Path, lo: float = 0.0, hi: float | None = None) -> list[float]:
    """Where a drawn road is cut into pieces: evenly along every straight
    that can hold at least two pieces of `config.AUTO_NODE_SPACING`, and
    nowhere else. `lo` and `hi` bound the part of the path that is plain
    road - a taper at either end is never cut.

    Only straights, because a cut through a fillet would put a node at a
    kink and turn a smooth corner into a two-arm junction. A straight piece
    of the fitted path already excludes the tangent lengths its fillets took,
    so every station here lands on plain road, at least a spacing from
    anything that bends. Pieces come out between one and two spacings long -
    rounding *down* rather than up, so a cut never leaves a piece shorter
    than the road would have been left uncut.
    """
    hi = path.length if hi is None else hi
    stations: list[float] = []
    for piece, start in zip(path.pieces, path.piece_starts):
        if not isinstance(piece, LineSegment):
            continue
        s0, s1 = max(start, lo), min(start + piece.length, hi)
        span = s1 - s0
        count = math.floor(span / config.AUTO_NODE_SPACING)
        if count < 2:
            continue
        for k in range(1, count):
            stations.append(s0 + span * k / count)
    return stations


def partition_corners(
    points: list[Vec2], path: Path, stations: list[float]
) -> list[list[Vec2]]:
    """Split a road's corner list at `stations` along its fitted path.

    Each corner belongs to the piece whose station range holds its fillet,
    found by projecting the corner onto the path - the nearest point of a
    corner is the belly of its own arc. The cut points become the last and
    first control point of the pieces either side, so the pieces refit to
    exactly the straight they were cut from and every fillet stays whole.
    """
    interior = points[1:-1]
    where = [path.project(corner) for corner in interior]
    parts: list[list[Vec2]] = []
    current = [points[0]]
    j = 0
    for s in stations:
        while j < len(interior) and where[j] < s:
            current.append(interior[j])
            j += 1
        cut = path.sample(s).position
        current.append(cut)
        parts.append(current)
        current = [cut]
    current.extend(interior[j:])
    current.append(points[-1])
    parts.append(current)
    return parts


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
    start_c: float | None = None,
    end_c: float | None = None,
) -> RoadPlan:
    """Build the road's command and try it on a ghost of the network.

    Called every frame for the preview and once more for the commit, with a
    fresh command each time: a command remembers the ids it allocated, so the
    one the ghost ran is a redo waiting to happen, not a first do.
    """
    command = build_road_command(ctx, points, start, end, start_c, end_c)
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
    would split, the node a `NODE` snap would join. A free snap acts on
    nothing, so it lights nothing."""
    if snap is None:
        return []
    if snap.node_id is not None:
        return [Highlight.node(snap.node_id)]
    if snap.segment_hit is not None:
        return [Highlight.segment(snap.segment_hit[0])]
    return []


def _endpoint(steps: list[Command], point: Vec2, snap: Snap | None) -> NodeSlot:
    """Turn one end of the stroke into a node id, adding commands as needed."""
    if snap is not None and snap.node_id is not None:
        return NodeSlot(snap.node_id)
    if snap is not None and snap.segment_hit is not None:
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
    """Both ends on the same node - a loop."""
    return (
        a is not None
        and b is not None
        and a.node_id is not None
        and a.node_id == b.node_id
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
    return ctx.snapper.snap(ctx.cursor, beside=(ctx.profile,), over_body=True)


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
    if snap.node_id is not None:
        node = network.nodes.get(snap.node_id)
        if node is None:
            return []
        arms = []
        for segment_id in node.segments:
            segment = network.segments.get(segment_id)
            if segment is not None:
                arms.append(segment.outgoing_dir(segment.is_at_a(node.id)))
        return arms
    if snap.segment_hit is not None:
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
