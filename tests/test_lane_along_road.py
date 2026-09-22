"""Joining a road *along* another road, and running alongside one (D23, D25).

Three claims. Hovering anywhere over a road's carriageway attaches at the
station under the cursor, and drawing onto it splits the road there and
arranges the new road across it by which side the cursor was on - exactly.
The footprint disc, before a first point, sits where that arranged body would
be rather than on the centreline it hangs off. And a free point near another
road is pulled sideways until its kerb runs a verge from the neighbour's - for
the draw tool with the profile the road will actually be built with, and for
the move tool with the profiles of the roads meeting the dragged node.
"""

from __future__ import annotations

import pytest

from roadsim import config
from roadsim.editor.context import EditorContext
from roadsim.editor.snapping import SnapKind, Snapper
from roadsim.editor.tools.draw_road import DrawRoadTool, build_road_command, plan_road
from roadsim.editor.tools.move_node import MoveNodeTool
from roadsim.geometry import Vec2
from roadsim.render.camera import Camera
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


# -- attaching along a road ---------------------------------------------------------


def test_anywhere_over_the_carriageway_attaches_at_that_station(ctx):
    segment = ctx.network.segments[1]
    half = segment.profile.half_width
    for y in (-half * 0.95, -2.0, 0.0, 3.5, half * 0.95):
        snap = ctx.snapper.snap(Vec2(30.0, y), over_body=True)
        assert snap.kind is SnapKind.SEGMENT
        assert snap.segment_hit == (segment.id, pytest.approx(230.0, abs=EXACT))
        assert_vec(snap.position, Vec2(30.0, 0.0))


def test_well_beside_a_road_is_not_over_it(ctx):
    segment = ctx.network.segments[1]
    far = segment.profile.half_width + 2 * config.SNAP_SEGMENT_PX / ZOOM
    assert ctx.snapper.over_segment(Vec2(30.0, far)) is None


def test_drawing_onto_a_road_from_its_south_side_splits_it_and_hugs_that_side(ctx):
    """The whole claim: one road becomes two at the station, a third joins the
    new node there, and it sits on the side of the road the cursor came from."""
    segment = ctx.network.segments[1]
    tool = DrawRoadTool()
    tool.place(ctx, Vec2(-180.0, -40.0))
    kerb = _kerb(segment, -1)
    end = tool.place(ctx, kerb + Vec2(0.0, 0.5))  # arriving shallow, south side
    assert end.kind is SnapKind.SEGMENT
    tool._commit(ctx)
    ctx.network.rebuild_dirty()

    assert segment.id not in ctx.network.segments
    # Two halves of the avenue, the slide taper at the join, and the road.
    assert len(ctx.network.segments) == 4
    mid = ctx.network.node_at(Vec2(-100.0, 0.0))
    assert mid is not None and mid.degree == 3

    taper = next(s for s in ctx.network.segments.values() if s.is_transition)
    road = next(
        s
        for s in ctx.network.segments.values()
        if s.profile.lanes == RESIDENTIAL_TWO_WAY.lanes and not s.is_transition
    )
    assert taper.node_b == mid.id
    # The road is centred on its own nodes (D28); the arrangement lives at the
    # taper's junction mouth, shifted toward the side the cursor was on.
    assert road.profile.datum == pytest.approx(0.0, abs=EXACT)
    assert taper.profile.datum == pytest.approx(0.0, abs=EXACT)
    assert taper.profile_b.datum < 0.0
    # Arranged *laterally*, in the mouth's own frame (D25): the body centre
    # projects onto the chosen arrangement across the avenue.
    room = (AVENUE_FOUR_LANE.total_width - RESIDENTIAL_TWO_WAY.total_width) / 2.0
    # At the node itself, not the trimmed mouth: the junction pulls the taper
    # arm back like any other, but the arrangement was measured at the node.
    frame = taper.frame_at(taper.length, False)
    target = Vec2(-100.0, -room)
    assert taper.profile_b.datum == pytest.approx(
        (target - frame.position).dot(frame.normal), abs=EXACT
    )


def test_drawing_onto_a_road_is_one_undo_step(ctx):
    segment = ctx.network.segments[1]
    tool = DrawRoadTool()
    tool.place(ctx, Vec2(-180.0, -40.0))
    tool.place(ctx, _kerb(segment, -1) + Vec2(0.0, 0.5))
    tool._commit(ctx)
    ctx.network.rebuild_dirty()
    assert len(ctx.network.segments) == 4

    ctx.undo()
    ctx.network.rebuild_dirty()
    assert set(ctx.network.segments) == {segment.id}
    assert len(ctx.network.nodes) == 2
    assert ctx.history.depth == 0


def test_both_ends_over_one_road_is_refused_rather_than_corrupting_it(ctx):
    segment = ctx.network.segments[1]
    tool = DrawRoadTool()
    a = tool._snap_world(ctx, Vec2(-100.0, -segment.profile.extent_right))
    b = tool._snap_world(ctx, Vec2(100.0, -segment.profile.extent_right))
    assert isinstance(build_road_command(ctx, [a.position, b.position], a, b), str)


# -- the preview ----------------------------------------------------------------


def test_hovering_a_road_offers_no_handles_and_lights_the_road(ctx):
    tool = DrawRoadTool()
    tool._raw = Vec2(50.0, 0.0)
    tool._hover = tool._snap_world(ctx, tool._raw)
    ctx.cursor = tool._hover.position
    preview = tool.preview(ctx)
    assert preview.handles == []
    assert [h.id for h in preview.highlights] == [1]


def test_the_footprint_moves_to_where_the_body_would_be_not_the_centreline(ctx):
    """Aim at the avenue's right kerb: the disc's own kerb sits on that kerb,
    and its centre is off the centreline by exactly the arrangement the click
    would choose. The road type reads where the road will be."""
    segment = ctx.network.segments[1]
    tool = DrawRoadTool()
    kerb = _kerb(segment, -1)
    tool._raw = kerb
    tool._hover = tool._snap_world(ctx, kerb)
    ctx.cursor = tool._hover.position
    preview = tool.preview(ctx)

    assert preview.footprint is not None
    assert preview.footprint != ctx.cursor
    own_half = RESIDENTIAL_TWO_WAY.total_width / 2.0
    assert_vec(preview.footprint - Vec2(0.0, own_half), kerb)


def test_the_footprint_stays_under_the_cursor_in_open_space(ctx):
    tool = DrawRoadTool()
    tool._raw = Vec2(0.0, 300.0)
    ctx.cursor = Vec2(0.0, 300.0)
    assert tool.preview(ctx).footprint == ctx.cursor


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


def test_beside_is_not_offered_without_a_profile_to_lay_alongside(ctx):
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
    not alignments: the only positions offered leave the bodies apart."""
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
    arranged, or the parallel run sits a lane off. Two placed points fix the
    start frame, so the answer is exact - and the verge is what lets the
    junction at the start resolve its gore at all."""
    segment = ctx.network.segments[1]
    ctx.select_profile(ONE_WAY_TWO_LANE.name)
    tool = DrawRoadTool()
    start_raw = _kerb(segment, -1) + Vec2(0.0, 0.5)
    start = tool.place(ctx, start_raw)
    assert start.kind is SnapKind.SEGMENT
    # The datum depends only on the direction the ramp leaves in, so fix that
    # first, read the shifted profile, then put the corner on that same ray at
    # the flush height so the final leg runs exactly parallel.
    leave = Vec2(4.0, -1.0).normalized()
    # Far enough out that the corner is not itself over the avenue - a point
    # placed over a road attaches to it, which is the point of D24.
    tool.place(ctx, start.position + leave * 60.0)  # locks the south side
    assert tool.arrangement is not None and tool.arrangement < 0.0
    shifted = tool._profile_if_ended_at(ctx, Vec2(60.0, -12.0))
    flush = _flush(segment, shifted)
    corner = start.position + leave * (flush / leave.y)
    tool.points[-1] = corner
    assert tool._profile_if_ended_at(ctx, Vec2(60.0, flush)).datum == pytest.approx(
        shifted.datum, abs=EXACT
    )
    end = tool._snap_world(ctx, Vec2(60.0, flush - 0.3))
    assert end.kind is SnapKind.BESIDE

    plan = plan_road(
        ctx, [*tool.points, end.position], start, end, tool.arrangement, None
    )
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
