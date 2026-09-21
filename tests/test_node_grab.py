"""Grabbing a node by a lane, at the editor layer.

`tests/test_lane_handle.py` proves the model formula in isolation; this file
proves the wiring - `Snapper.nearest_lane_handle`, `node_grab.grab_at` and
`MoveNodeTool` - drives that formula the same way a real drag would, with no
window and no mouse (the same reasoning `test_tools.py` states for every other
tool).
"""

from __future__ import annotations

import pytest

from roadsim.editor.context import EditorContext
from roadsim.editor.handle import HandleKind
from roadsim.editor.node_grab import grab_at
from roadsim.editor.snapping import SnapKind
from roadsim.editor.tools.move_node import MoveNodeTool
from roadsim.geometry import Vec2
from roadsim.render.camera import Camera
from roadsim.road.lane_handle import LaneHandleKind, segment_end_handles
from roadsim.road.network import RoadNetwork
from roadsim.road.presets import AVENUE_FOUR_LANE, RESIDENTIAL_TWO_WAY

from .conftest import assert_vec

A_START, A_END = Vec2(-100.0, 0.0), Vec2(-40.0, 0.0)
B_START, B_END = Vec2(40.0, 0.0), Vec2(100.0, 0.0)


@pytest.fixture
def ctx() -> EditorContext:
    """A 2-lane road and a 4-lane road, side by side but not touching."""
    network = RoadNetwork()
    network.connect(A_START, A_END, RESIDENTIAL_TWO_WAY)
    network.connect(B_START, B_END, AVENUE_FOUR_LANE)
    network.rebuild_all()
    return EditorContext(network, Camera(zoom=10.0, viewport=(1440, 900)))


# -- Snapper.nearest_lane_handle --------------------------------------------


def test_nearest_lane_handle_finds_a_handle_within_reach(ctx):
    seg_a = ctx.network.segments[1]
    handle = segment_end_handles(seg_a, seg_a.node_b, False)[0]

    snap = ctx.snapper.nearest_lane_handle(handle.position)
    assert snap is not None
    assert snap.kind is SnapKind.LANE
    assert_vec(snap.position, handle.position)


def test_nearest_lane_handle_returns_none_far_from_every_node(ctx):
    assert ctx.snapper.nearest_lane_handle(Vec2(0.0, 500.0)) is None


def test_nearest_lane_handle_respects_ignore_sets(ctx):
    seg_a = ctx.network.segments[1]
    handle = segment_end_handles(seg_a, seg_a.node_b, False)[0]

    ignored = ctx.snapper.nearest_lane_handle(
        handle.position, ignore_segments=frozenset({seg_a.id})
    )
    assert ignored is None


# -- node_grab.grab_at --------------------------------------------------------


def test_grab_at_a_lane_handle_carries_its_lever(ctx):
    seg_a = ctx.network.segments[1]
    handle = next(
        h
        for h in segment_end_handles(seg_a, seg_a.node_b, False)
        if h.kind is LaneHandleKind.LANE
    )

    grab = grab_at(ctx, handle.position)
    assert grab is not None
    assert grab.node_id == seg_a.node_b
    assert grab.handle is not None
    assert_vec(grab.lever, handle.lever)


def test_grab_at_the_plain_node_carries_a_zero_lever(ctx):
    """A click near the node but outside `SNAP_LANE_PX` reach falls through to
    the plain node grab, whose lever is always zero.

    (`RESIDENTIAL_TWO_WAY` is a symmetric two-way profile, so its own middle
    edge sits at offset 0 - exactly on the node. That handle would have the
    same zero lever anyway; this click is deliberately far enough off to prove
    the *fallback* path, not just the coincidence.)
    """
    node = ctx.network.node_at(A_END)
    click = node.position + Vec2(1.0, 0.0)  # along the road, clear of every lateral handle

    grab = grab_at(ctx, click)
    assert grab is not None
    assert grab.node_id == node.id
    assert grab.handle is None
    assert_vec(grab.lever, Vec2(0.0, 0.0))


def test_grab_at_empty_space_finds_nothing(ctx):
    assert grab_at(ctx, Vec2(500.0, 500.0)) is None


# -- MoveNodeTool, end to end -------------------------------------------------


def test_dragging_by_a_lane_handle_lands_that_lane_on_the_drop():
    """The user-facing version of the flip-free claim: grab the 2-lane road's
    lane, drop it on the 4-lane road's lane, release - the two lane
    centrelines meet exactly, with no other code path involved.

    A's far end (not being dragged) is built already at the y its dragged end
    must land on, so the move is a pure translation with no residual from the
    frozen lever rotating the segment mid-drag - see
    `tests/test_lane_handle.py`'s equivalent model-level test for why, and
    `docs/decisions.md` D18 for the residual itself.
    """
    grab_index, target_index = 1, 4
    a_y = AVENUE_FOUR_LANE.lane_center(target_index) - RESIDENTIAL_TWO_WAY.lane_center(
        grab_index
    )

    network = RoadNetwork()
    network.connect(Vec2(-100.0, a_y), Vec2(-40.0, a_y), RESIDENTIAL_TWO_WAY)
    network.connect(B_START, B_END, AVENUE_FOUR_LANE)
    network.rebuild_all()
    ctx = EditorContext(network, Camera(zoom=10.0, viewport=(1440, 900)))

    seg_a, seg_b = network.segments[1], network.segments[2]
    grab_handle = next(
        h
        for h in segment_end_handles(seg_a, seg_a.node_b, False)
        if h.kind is LaneHandleKind.LANE and h.index == grab_index
    )
    target_handle = next(
        h
        for h in segment_end_handles(seg_b, seg_b.node_a, True)
        if h.kind is LaneHandleKind.LANE and h.index == target_index
    )

    tool = MoveNodeTool()
    assert tool.grab(ctx, grab_handle.position)
    assert tool.grab_state.handle is not None

    tool.drag_to(ctx, target_handle.position - tool.grab_state.lever)
    tool.release(ctx)
    ctx.network.rebuild_dirty()

    seg_a = ctx.network.segments[seg_a.id]
    lane_a = seg_a.lane_centerline(grab_index)
    assert_vec(lane_a.end.position, target_handle.position)


def test_dragging_by_the_plain_centre_handle_is_unchanged(ctx):
    """`lever == Vec2(0, 0)` must reproduce exactly what the tool already did
    before any of this - a plain node-to-node move."""
    node = ctx.network.node_at(A_END)
    click = node.position + Vec2(1.0, 0.0)  # along the road, clear of every lateral handle
    target = Vec2(-40.0, 30.0)

    tool = MoveNodeTool()
    assert tool.grab(ctx, click)
    assert tool.grab_state.handle is None
    tool.drag_to(ctx, target)
    tool.release(ctx)

    assert_vec(ctx.network.nodes[node.id].position, target)
    assert ctx.history.depth == 1


# -- preview: the lane rings the overlay actually draws ----------------------


def test_hovering_a_node_publishes_its_lane_and_edge_handles(ctx):
    tool = MoveNodeTool()
    ctx.cursor = A_END

    preview = tool.preview(ctx)
    kinds = {h.kind for h in preview.handles}
    assert kinds == {HandleKind.LANE, HandleKind.EDGE}
    assert not any(h.active for h in preview.handles)  # nothing grabbed yet


def test_dragging_by_a_handle_marks_it_active_in_the_preview(ctx):
    seg_a = ctx.network.segments[1]
    handle = next(
        h
        for h in segment_end_handles(seg_a, seg_a.node_b, False)
        if h.kind is LaneHandleKind.LANE
    )

    tool = MoveNodeTool()
    assert tool.grab(ctx, handle.position)
    preview = tool.preview(ctx)

    active = [h for h in preview.handles if h.active]
    assert len(active) == 1
    assert_vec(active[0].position, handle.position)


def test_preview_has_no_handles_far_from_any_node(ctx):
    tool = MoveNodeTool()
    ctx.cursor = Vec2(500.0, 500.0)
    assert tool.preview(ctx).handles == []


# -- dropping on another road's lane connects the two (D20) ------------------


def test_dropping_on_another_lane_merges_and_aligns(ctx):
    seg_a = ctx.network.segments[1]
    seg_b = ctx.network.segments[2]
    grab_handle = next(
        h
        for h in segment_end_handles(seg_a, seg_a.node_b, False)
        if h.kind is LaneHandleKind.LANE and h.index == 1
    )
    target_handle = next(
        h
        for h in segment_end_handles(seg_b, seg_b.node_a, True)
        if h.kind is LaneHandleKind.LANE and h.index == 4
    )

    tool = MoveNodeTool()
    assert tool.grab(ctx, grab_handle.position)

    ctx.cursor = target_handle.position
    tool.drag_to(ctx, tool._target(ctx))  # exercises _target, same as a real drag
    tool.release(ctx)
    ctx.network.rebuild_dirty()

    seg_a = ctx.network.segments[seg_a.id]
    seg_b = ctx.network.segments[seg_b.id]
    assert seg_a.node_b == seg_b.node_a  # one shared node now
    assert grab_handle.node_id not in ctx.network.nodes
    assert ctx.history.depth == 1

    # The taper actually has something to render: the junction model sees a
    # real two-arm join, not a through-joint with nothing painted.
    shared = seg_a.node_b
    junction = ctx.network.junctions.get(shared)
    assert junction is not None
    assert len(junction.ends) == 2

    lane_a = seg_a.lane_centerline(1)
    lane_b = seg_b.lane_centerline(4)
    assert_vec(lane_a.end.position, lane_b.start.position)


def test_dropping_on_open_space_still_just_moves_the_node(ctx):
    """Nothing about the plain move is disturbed by any of this."""
    seg_a = ctx.network.segments[1]
    grab_handle = next(
        h
        for h in segment_end_handles(seg_a, seg_a.node_b, False)
        if h.kind is LaneHandleKind.LANE
    )
    tool = MoveNodeTool()
    tool.grab(ctx, grab_handle.position)
    target = Vec2(-40.0, 40.0)
    tool.drag_to(ctx, target - grab_handle.lever)
    tool.release(ctx)

    assert ctx.network.nodes[seg_a.node_b].position == target - grab_handle.lever
    assert len(ctx.network.nodes) == 4  # nothing merged


def test_undoing_a_connect_restores_two_separate_roads(ctx):
    seg_a = ctx.network.segments[1]
    seg_b = ctx.network.segments[2]
    before_node_count = len(ctx.network.nodes)
    grab_handle = next(
        h
        for h in segment_end_handles(seg_a, seg_a.node_b, False)
        if h.kind is LaneHandleKind.LANE and h.index == 1
    )
    target_handle = next(
        h
        for h in segment_end_handles(seg_b, seg_b.node_a, True)
        if h.kind is LaneHandleKind.LANE and h.index == 4
    )

    tool = MoveNodeTool()
    tool.grab(ctx, grab_handle.position)
    ctx.cursor = target_handle.position
    tool.drag_to(ctx, tool._target(ctx))
    tool.release(ctx)
    ctx.network.rebuild_dirty()
    assert len(ctx.network.nodes) == before_node_count - 1

    ctx.undo()
    ctx.network.rebuild_dirty()
    assert len(ctx.network.nodes) == before_node_count
    assert ctx.network.segments[seg_a.id].node_b != ctx.network.segments[seg_b.id].node_a
