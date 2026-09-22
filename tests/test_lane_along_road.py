"""Joining a road by a lane *along* another road, and running alongside one (D23).

Three claims. A lane handle exists at any station of a road, not only at its
nodes, and drawing onto one splits the road there and shifts the new road so
the chosen lane lines up - exactly, the same claim `test_lane_draw.py` makes at
a node. The footprint disc, before a first point, sits where that shifted
road's body would be rather than on the centreline it hangs off. And a free
point near another road is pulled sideways until its kerb runs a verge from
the neighbour's - for the draw tool with the profile the road will actually be
built with, and for the move tool with the profiles of the roads meeting the
dragged node.
"""

from __future__ import annotations

import pytest

from roadsim import config
from roadsim.editor.context import EditorContext
from roadsim.editor.handle import HandleKind
from roadsim.editor.lane_draw import footprint_on_lane, lane_candidates
from roadsim.editor.snapping import SnapKind, Snapper
from roadsim.editor.tools.draw_road import DrawRoadTool, build_road_command, plan_road
from roadsim.editor.tools.move_node import MoveNodeTool
from roadsim.geometry import Vec2
from roadsim.render.camera import Camera
from roadsim.road.lane_handle import (
    LaneHandleKind,
    handles_beside,
    segment_lane_handles,
)
from roadsim.road.network import RoadNetwork
from roadsim.road.presets import AVENUE_FOUR_LANE, ONE_WAY_TWO_LANE, RESIDENTIAL_TWO_WAY

from .conftest import EXACT, assert_vec

ZOOM = 10.0


@pytest.fixture
def ctx() -> EditorContext:
    """One long 4-lane avenue running east, and nothing else in the world."""
    network = RoadNetwork()
    network.connect(Vec2(-200.0, 0.0), Vec2(200.0, 0.0), AVENUE_FOUR_LANE)
    network.rebuild_all()
    editor = EditorContext(network, Camera(zoom=ZOOM, viewport=(1440, 900)))
    editor.select_profile(RESIDENTIAL_TWO_WAY.name)
    return editor


def _kerb(segment, side: float) -> Vec2:
    """A point on the avenue's kerb at x = -100: +1 the left (north) kerb, -1 the right."""
    extent = segment.profile.extent_left if side > 0 else segment.profile.extent_right
    return Vec2(-100.0, side * extent)


# -- the handles themselves ---------------------------------------------------


def test_handles_along_a_road_hang_off_the_centreline_at_that_station(ctx):
    segment = ctx.network.segments[1]
    s = 130.0
    frame = segment.path.sample(s)
    for handle in segment_lane_handles(segment, s):
        assert handle.node_id is None
        assert handle.station == pytest.approx(s, abs=EXACT)
        assert_vec(handle.centre, frame.position)
        assert_vec(handle.position, frame.position + frame.normal * handle.offset)


def test_along_a_road_the_offsets_are_the_same_list_a_node_publishes(ctx):
    """One set of candidates whatever the station, so what a datum can honour
    does not depend on where along the road you clicked."""
    segment = ctx.network.segments[1]
    at_node = {h.offset for h in segment_lane_handles(segment, 0.0, segment.node_a, True)}
    along = {h.offset for h in segment_lane_handles(segment, 77.0)}
    assert along == at_node == set(lane_candidates(segment.profile))


def test_handles_beside_returns_the_set_a_handle_came_from(ctx):
    segment = ctx.network.segments[1]
    along = segment_lane_handles(segment, 50.0)
    assert list(handles_beside(ctx.network, along[0])) == list(along)
    at_node = segment_lane_handles(segment, 0.0, segment.node_a, True)
    beside = handles_beside(ctx.network, at_node[0])
    assert all(h in beside for h in at_node)


# -- snapping to one -----------------------------------------------------------


def test_hovering_a_kerb_mid_road_snaps_to_that_kerb_edge(ctx):
    segment = ctx.network.segments[1]
    snap = ctx.snapper.nearest_lane_handle(_kerb(segment, -1) + Vec2(0.0, -0.2))
    assert snap is not None and snap.kind is SnapKind.LANE
    handle = snap.lane_handle
    assert handle.kind is LaneHandleKind.EDGE
    assert handle.node_id is None
    assert handle.offset == pytest.approx(-segment.profile.extent_right, abs=EXACT)
    assert handle.station == pytest.approx(100.0, abs=EXACT)


def test_anywhere_over_the_carriageway_names_the_nearest_lane_line(ctx):
    """No dead gaps between two lane lines where the cursor falls through to
    the grid and the ghost goes red for crossing the road it is over."""
    segment = ctx.network.segments[1]
    half = segment.profile.half_width
    steps = 37  # not a divisor of any lane width, so no y ties two lines
    for i in range(steps + 1):
        y = -half + (2 * half) * i / steps
        snap = ctx.snapper.nearest_lane_handle(Vec2(30.0, y))
        assert snap is not None and snap.kind is SnapKind.LANE
        # The nearest, not merely one within reach.
        offsets = lane_candidates(segment.profile)
        assert snap.lane_handle.offset == pytest.approx(
            min(offsets, key=lambda o: abs(o - y)), abs=EXACT
        )


def test_well_beside_a_road_is_not_over_it(ctx):
    segment = ctx.network.segments[1]
    far = segment.profile.half_width + 2 * config.SNAP_LANE_PX / ZOOM
    assert ctx.snapper.nearest_lane_handle(Vec2(30.0, far)) is None


def test_near_a_node_the_nodes_own_handles_win(ctx):
    segment = ctx.network.segments[1]
    node = ctx.network.nodes[segment.node_a]
    just_inside = node.position + Vec2(config.SNAP_NODE_PX / ZOOM * 0.3, 0.0)
    snap = ctx.snapper.nearest_lane_handle(just_inside)
    assert snap is not None
    assert snap.lane_handle.node_id == segment.node_a


def test_a_mid_road_lane_snap_attaches_at_the_centreline_and_names_the_split(ctx):
    segment = ctx.network.segments[1]
    snap = ctx.snapper.nearest_lane_handle(_kerb(segment, -1))
    assert snap.attach_node_id is None
    assert snap.segment_hit == (segment.id, pytest.approx(100.0, abs=EXACT))
    assert_vec(snap.attach_position, Vec2(-100.0, 0.0))
    assert not snap.is_free


# -- drawing onto one ----------------------------------------------------------


def test_drawing_onto_a_mid_road_lane_splits_the_road_and_lines_the_lane_up(ctx):
    """The whole claim: one road becomes two at the station, a third joins the
    new node there, and one of its own lane lines sits on the kerb that was
    clicked to the last bit."""
    segment = ctx.network.segments[1]
    tool = DrawRoadTool()
    target = tool._snap_world(ctx, _kerb(segment, -1))
    # Arriving at a shallow angle, the way a merge does. A road arriving square
    # on has the kerb straight ahead of it, not beside it: its lateral offset
    # is zero and the join is the plain centreline one.
    far = tool._snap_world(ctx, Vec2(-180.0, -40.0))

    command = build_road_command(
        ctx, [far.attach_position, target.attach_position], far, target
    )
    ctx.apply(command)
    ctx.network.rebuild_dirty()

    assert segment.id not in ctx.network.segments
    assert len(ctx.network.segments) == 3
    mid = ctx.network.node_at(Vec2(-100.0, 0.0))
    assert mid is not None and mid.degree == 3

    new = next(s for s in ctx.network.segments.values() if s.profile.lanes == RESIDENTIAL_TWO_WAY.lanes)
    assert new.node_b == mid.id
    assert new.profile.datum != pytest.approx(0.0, abs=EXACT)
    # Lined up *laterally*, in the new road's own end frame (D21): a road that
    # arrives at an angle also sees the kerb some way along its tangent, and
    # that part is the junction's to close, not the datum's.
    frame = new.path.sample(new.path.length)
    lateral = (target.position - frame.position).dot(frame.normal)
    assert min(abs(o - lateral) for o in lane_candidates(new.profile)) == pytest.approx(
        0.0, abs=EXACT
    )


def test_drawing_onto_a_mid_road_lane_is_one_undo_step(ctx):
    segment = ctx.network.segments[1]
    tool = DrawRoadTool()
    target = tool._snap_world(ctx, _kerb(segment, -1))
    far = tool._snap_world(ctx, Vec2(-180.0, -40.0))
    ctx.apply(build_road_command(ctx, [far.attach_position, target.attach_position], far, target))
    ctx.network.rebuild_dirty()

    ctx.undo()
    ctx.network.rebuild_dirty()
    assert set(ctx.network.segments) == {segment.id}
    assert len(ctx.network.nodes) == 2
    assert ctx.history.depth == 0


def test_both_ends_on_lanes_of_one_road_is_refused_like_two_centreline_snaps(ctx):
    segment = ctx.network.segments[1]
    tool = DrawRoadTool()
    a = tool._snap_world(ctx, Vec2(-100.0, -segment.profile.extent_right))
    b = tool._snap_world(ctx, Vec2(100.0, -segment.profile.extent_right))
    assert isinstance(build_road_command(ctx, [a.attach_position, b.attach_position], a, b), str)


# -- the preview ----------------------------------------------------------------


def test_hovering_a_road_offers_the_handles_at_that_station(ctx):
    tool = DrawRoadTool()
    ctx.cursor = Vec2(50.0, 0.0)
    preview = tool.preview(ctx)
    kinds = {h.kind for h in preview.handles}
    assert kinds == {HandleKind.LANE, HandleKind.EDGE}
    assert all(h.position.x == pytest.approx(50.0, abs=EXACT) for h in preview.handles)
    assert sum(h.active for h in preview.handles) == 1


def test_the_footprint_moves_to_where_the_body_would_be_not_the_centreline(ctx):
    """Aim at the avenue's right kerb: the disc's own kerb sits on that kerb,
    and its centre is off the centreline by exactly the datum the click would
    produce. The road type reads where the road will be."""
    segment = ctx.network.segments[1]
    tool = DrawRoadTool()
    kerb = _kerb(segment, -1)
    tool._hover = tool._snap_world(ctx, kerb)
    ctx.cursor = tool._hover.attach_position
    preview = tool.preview(ctx)

    handle = tool._hover.lane_handle
    assert preview.footprint is not None
    assert preview.footprint != handle.centre
    own_half = RESIDENTIAL_TWO_WAY.total_width / 2.0
    assert_vec(preview.footprint - handle.normal * own_half, kerb)


def test_the_footprint_stays_under_the_cursor_in_open_space(ctx):
    tool = DrawRoadTool()
    ctx.cursor = Vec2(0.0, 300.0)
    assert tool.preview(ctx).footprint == ctx.cursor


def test_footprint_on_a_centre_edge_is_the_centre(ctx):
    segment = ctx.network.segments[1]
    centre = next(h for h in segment_lane_handles(segment, 20.0) if abs(h.offset) < EXACT)
    assert_vec(footprint_on_lane(RESIDENTIAL_TWO_WAY, centre), centre.centre)


# -- alongside another road -----------------------------------------------------


def _snapper(ctx: EditorContext) -> Snapper:
    return ctx.snapper


def _flush(other, own) -> float:
    """The y a road of profile `own` sits at to run just south of `other`."""
    return -(other.profile.extent_right + config.BESIDE_GAP + own.extent_left)


def test_beside_pulls_a_point_sideways_until_the_kerbs_are_a_verge_apart(ctx):
    segment = ctx.network.segments[1]
    own = RESIDENTIAL_TWO_WAY
    flush = _flush(segment, own)
    snap = _snapper(ctx).snap(Vec2(37.0, flush - 0.5), beside=(own,))
    assert snap.kind is SnapKind.BESIDE
    assert_vec(snap.position, Vec2(37.0, flush))
    assert snap.is_free
    assert_vec(snap.beside.kerb, Vec2(37.0, -segment.profile.extent_right))
    assert_vec(snap.beside.tangent, Vec2(1.0, 0.0))


def test_beside_is_not_offered_without_a_profile_to_lay_flush(ctx):
    segment = ctx.network.segments[1]
    flush = _flush(segment, RESIDENTIAL_TWO_WAY)
    assert _snapper(ctx).snap(Vec2(37.0, flush - 0.5)).kind is not SnapKind.BESIDE


def test_beside_does_not_reach_past_the_end_of_the_road(ctx):
    segment = ctx.network.segments[1]
    flush = _flush(segment, RESIDENTIAL_TWO_WAY)
    beyond = Vec2(200.0 + 5.0, flush)
    assert _snapper(ctx).snap(beyond, beside=(RESIDENTIAL_TWO_WAY,)).kind is not SnapKind.BESIDE


def test_beside_never_puts_one_carriageway_through_another(ctx):
    """Lane-on-lane alignments between two side-by-side roads are overlaps,
    not alignments: the only positions offered leave the bodies just touching."""
    segment = ctx.network.segments[1]
    own = ONE_WAY_TWO_LANE
    for y in (-2.0, 0.0, 3.0, -8.0):
        snap = _snapper(ctx).snap(Vec2(37.0, y), beside=(own,))
        assert snap.kind is not SnapKind.BESIDE


def test_the_reach_is_in_pixels(ctx):
    segment = ctx.network.segments[1]
    own = RESIDENTIAL_TWO_WAY
    flush = _flush(segment, own)
    off = config.SNAP_BESIDE_PX / ZOOM * 0.9
    near = Snapper(ctx.network, Camera(zoom=ZOOM, viewport=(1440, 900)))
    far = Snapper(ctx.network, Camera(zoom=ZOOM * 4, viewport=(1440, 900)))
    assert near.snap(Vec2(37.0, flush - off), beside=(own,)).kind is SnapKind.BESIDE
    assert far.snap(Vec2(37.0, flush - off), beside=(own,)).kind is not SnapKind.BESIDE


def test_dragging_a_node_lays_its_road_alongside_a_neighbour(ctx):
    """The move tool's proximity snap: the dragged road's own kerb - of its
    own, possibly shifted, profile - lands a verge from the avenue's exactly."""
    segment = ctx.network.segments[1]
    other = ctx.network.connect(Vec2(20.0, -60.0), Vec2(80.0, -60.0), RESIDENTIAL_TWO_WAY)
    ctx.network.rebuild_all()
    flush = _flush(segment, other.profile)

    tool = MoveNodeTool()
    assert tool.grab(ctx, Vec2(80.0, -60.0))
    ctx.cursor = Vec2(90.0, flush - 0.4)
    tool.drag_to(ctx, tool._target(ctx))
    assert tool.preview(ctx).snap.kind is SnapKind.BESIDE
    tool.release(ctx)
    ctx.network.rebuild_dirty()

    moved = ctx.network.segments[other.id]
    assert_vec(ctx.network.nodes[moved.node_b].position, Vec2(90.0, flush))
    assert flush + moved.profile.extent_left == pytest.approx(
        -segment.profile.extent_right - config.BESIDE_GAP, abs=EXACT
    )


def test_a_ramp_leaves_a_lane_and_runs_alongside_with_its_shifted_profile(ctx):
    """The shape this is all for: start on the avenue's outer kerb, diverge,
    run parallel. The end snap has to be solved for the profile the start
    shifted, or the parallel run sits a lane off. Two placed points fix the
    start frame, so the answer is exact - and the verge is what lets the
    junction at the start resolve its gore at all."""
    segment = ctx.network.segments[1]
    ctx.select_profile(ONE_WAY_TWO_LANE.name)
    tool = DrawRoadTool()
    start = tool._snap_world(ctx, _kerb(segment, -1) + Vec2(0.0, -0.2))
    tool.start_snap = start
    # The datum depends only on the direction the ramp leaves in, so fix that
    # first, read the shifted profile, then put the corner on that same ray at
    # the flush height so the final leg runs exactly parallel.
    leave = Vec2(4.0, -1.0).normalized()
    tool.points = [start.attach_position, start.attach_position + leave * 40.0]
    shifted = tool._profile_if_ended_at(ctx, Vec2(60.0, -12.0))
    flush = _flush(segment, shifted)
    corner = start.attach_position + leave * (flush / leave.y)
    tool.points = [start.attach_position, corner]
    assert tool._profile_if_ended_at(ctx, Vec2(60.0, flush)).datum == pytest.approx(
        shifted.datum, abs=EXACT
    )
    end = tool._snap_world(ctx, Vec2(60.0, flush - 0.3))
    assert end.kind is SnapKind.BESIDE

    plan = plan_road(ctx, [*tool.points, end.position], start, end)
    assert not plan.invalid, plan.reason
    ctx.apply(plan.command)
    ctx.network.rebuild_dirty()

    ramp = max(ctx.network.segments.values(), key=lambda s: s.id)
    frame = ramp.path.sample(ramp.path.length)
    assert_vec(frame.tangent, Vec2(1.0, 0.0))
    upper_kerb = frame.position + frame.normal * ramp.profile.extent_left
    assert upper_kerb.y == pytest.approx(
        -segment.profile.extent_right - config.BESIDE_GAP, abs=EXACT
    )
