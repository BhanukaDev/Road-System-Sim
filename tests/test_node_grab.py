"""Grabbing and dragging a node, at the editor layer.

Moving a node is a position and nothing else (D21): one centre handle, no lane
rings, and no connection made by where it lands. How a narrower road arranges
itself across a wider one is the draw tool's business (D25,
`tests/test_lane_draw.py`); this file is where that boundary is asserted.
"""

from __future__ import annotations

import pytest

from roadsim.editor.context import EditorContext
from roadsim.editor.node_grab import grab_at
from roadsim.editor.tools.move_node import MoveNodeTool
from roadsim.geometry import Vec2
from roadsim.render.camera import Camera
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


def _lane_point(segment, at_a: bool, lane: int) -> Vec2:
    """Where lane `lane` of `segment` meets its `at_a` end."""
    frame = segment.path.sample(0.0 if at_a else segment.path.length)
    return frame.position + frame.normal * segment.profile.lane_center(lane)


# -- node_grab.grab_at --------------------------------------------------------


def test_grab_at_a_node_takes_the_node_itself(ctx):
    node = ctx.network.node_at(A_END)
    grab = grab_at(ctx, node.position + Vec2(1.0, 0.0))
    assert grab is not None
    assert grab.node_id == node.id
    assert_vec(grab.origin, node.position)


def test_a_lane_centre_at_a_node_is_not_a_grab_target(ctx):
    """A lane centre sits a lane off the node, well outside `SNAP_NODE_PX`.
    Clicking one while moving takes hold of nothing at all - the tool has no
    second thing to offer there (D21)."""
    seg_a = ctx.network.segments[1]
    on_lane = _lane_point(seg_a, at_a=False, lane=0)
    assert on_lane.distance_to(ctx.network.nodes[seg_a.node_b].position) > 1.0

    assert grab_at(ctx, on_lane) is None


def test_grab_at_empty_space_finds_nothing(ctx):
    assert grab_at(ctx, Vec2(500.0, 500.0)) is None


# -- MoveNodeTool, end to end -------------------------------------------------


def test_a_drag_moves_the_node_and_leaves_one_undo_step(ctx):
    node = ctx.network.node_at(A_END)
    target = Vec2(-40.0, 30.0)

    tool = MoveNodeTool()
    assert tool.grab(ctx, node.position)
    tool.drag_to(ctx, Vec2(-40.0, 10.0))
    tool.drag_to(ctx, target)
    tool.release(ctx)

    assert_vec(ctx.network.nodes[node.id].position, target)
    assert ctx.history.depth == 1


def test_cancelling_a_drag_puts_the_node_back(ctx):
    node = ctx.network.node_at(A_END)
    tool = MoveNodeTool()
    tool.grab(ctx, node.position)
    tool.drag_to(ctx, Vec2(-40.0, 30.0))
    tool.cancel(ctx)

    assert_vec(ctx.network.nodes[node.id].position, A_END)
    assert ctx.history.depth == 0


def test_dropping_on_another_roads_lane_only_moves_the_node(ctx):
    """The behaviour D20 gave this tool and D21 took away: landing on another
    road's lane merges nothing and connects nothing."""
    seg_a, seg_b = ctx.network.segments[1], ctx.network.segments[2]
    target = _lane_point(seg_b, at_a=True, lane=4)
    before_nodes = len(ctx.network.nodes)

    tool = MoveNodeTool()
    tool.grab(ctx, ctx.network.nodes[seg_a.node_b].position)
    ctx.cursor = target
    tool.drag_to(ctx, tool._target(ctx))
    tool.release(ctx)
    ctx.network.rebuild_dirty()

    assert len(ctx.network.nodes) == before_nodes
    assert ctx.network.segments[seg_a.id].node_b != ctx.network.segments[seg_b.id].node_a
    assert ctx.network.segments[seg_a.id].profile.datum == pytest.approx(0.0, abs=1e-9)


# -- preview: no lane rings while moving -------------------------------------


def test_hovering_a_node_publishes_no_handles(ctx):
    tool = MoveNodeTool()
    ctx.cursor = A_END
    assert tool.preview(ctx).handles == []


def test_dragging_publishes_no_handles_either(ctx):
    tool = MoveNodeTool()
    tool.grab(ctx, A_END)
    tool.drag_to(ctx, Vec2(-40.0, 20.0))
    assert tool.preview(ctx).handles == []
