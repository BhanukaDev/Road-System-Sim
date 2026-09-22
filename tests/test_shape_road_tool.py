"""Reshaping a placed road, driven with no window and no mouse.

The same reasoning `test_tools.py` states for every other tool: a tool
produces commands and a preview, so its whole behaviour is reachable through
direct calls.
"""

from __future__ import annotations

import pytest

from roadsim.editor.context import EditorContext, Selection
from roadsim.editor.handle import HandleKind
from roadsim.editor.tools.shape_road import ShapeRoadTool
from roadsim.geometry import Vec2
from roadsim.render.camera import Camera
from roadsim.road.network import RoadNetwork
from roadsim.road.presets import RESIDENTIAL_TWO_WAY
from roadsim.road.shape_handle import ShapeHandleKind, shape_handles
from roadsim.serialization import dumps

from .conftest import assert_vec

ORIGIN = Vec2(0.0, 0.0)
EAST = Vec2(60.0, 0.0)


@pytest.fixture
def ctx() -> EditorContext:
    """One bent road (a real fillet) and one straight one."""
    network = RoadNetwork()
    network.connect(
        Vec2(-60.0, 0.0), Vec2(0.0, 60.0), RESIDENTIAL_TWO_WAY, via=[ORIGIN]
    )
    network.connect(Vec2(-60.0, -40.0), Vec2(60.0, -40.0), RESIDENTIAL_TWO_WAY)
    network.rebuild_all()
    return EditorContext(network, Camera(zoom=10.0, viewport=(1440, 900)))


# -- handles are published only for the selected road -----------------------


def test_no_selection_means_no_handles(ctx):
    tool = ShapeRoadTool()
    assert tool.preview(ctx).handles == []


def test_selecting_a_road_publishes_its_handles(ctx):
    ctx.select(Selection(segment=1))
    tool = ShapeRoadTool()

    kinds = {h.kind for h in tool.preview(ctx).handles}
    assert HandleKind.CONTROL in kinds
    assert HandleKind.ARC_MID in kinds
    assert HandleKind.ARC_END in kinds


def test_selecting_a_road_changes_nothing_on_disk():
    """Looking is not touching - a save of a road you only selected is
    byte-identical to one you never looked at."""
    network = RoadNetwork()
    network.connect(
        Vec2(-60.0, 0.0), Vec2(0.0, 60.0), RESIDENTIAL_TWO_WAY, via=[ORIGIN]
    )
    network.rebuild_all()
    before = dumps(network)

    ctx = EditorContext(network, Camera(zoom=10.0, viewport=(1440, 900)))
    ctx.select(Selection(segment=1))
    ShapeRoadTool().preview(ctx)

    assert dumps(network) == before


# -- clicking with no handle under it is not this tool's call (D24) -----------


def test_a_press_with_no_handle_under_it_grabs_nothing(ctx):
    """Selecting the road underneath is `tools/edit_road.py`'s job now; this
    tool only says whether a shape handle of the selected road was hit."""
    tool = ShapeRoadTool()
    assert not tool.grab(ctx, Vec2(-40.0, -40.0))  # on segment 2, unselected
    assert ctx.selection.is_empty
    ctx.select(Selection(segment=1))
    assert not tool.grab(ctx, Vec2(500.0, 500.0))
    assert ctx.selection == Selection(segment=1)


# -- dragging a STRAIGHT_MID materialises a point, invisibly ----------------


def test_dragging_a_straight_mid_bends_the_road_there():
    network = RoadNetwork()
    network.connect(ORIGIN, EAST, RESIDENTIAL_TWO_WAY)
    network.rebuild_all()
    ctx = EditorContext(network, Camera(zoom=10.0, viewport=(1440, 900)))
    ctx.select(Selection(segment=1))

    segment = network.segments[1]
    before_points = len(segment.control_points)
    handle = next(
        h for h in shape_handles(segment) if h.kind is ShapeHandleKind.STRAIGHT_MID
    )

    tool = ShapeRoadTool()
    assert tool.grab(ctx, handle.position)
    tool.drag_to(ctx, Vec2(30.0, 20.0))
    tool.release(ctx)

    segment = network.segments[1]
    assert len(segment.control_points) == before_points + 1
    assert_vec(segment.control_points[1], Vec2(30.0, 20.0))
    assert ctx.history.depth == 1


# -- dragging a CONTROL point moves it directly, with a zero lever ----------


def test_dragging_a_control_point_moves_it_exactly_to_the_cursor(ctx):
    ctx.select(Selection(segment=1))
    segment = ctx.network.segments[1]
    handle = next(
        h for h in shape_handles(segment) if h.kind is ShapeHandleKind.CONTROL
    )
    target = Vec2(-10.0, 15.0)

    tool = ShapeRoadTool()
    assert tool.grab(ctx, handle.position)
    tool.drag_to(ctx, target)
    tool.release(ctx)

    segment = ctx.network.segments[1]
    assert_vec(segment.control_points[handle.control_index], target)


# -- dragging an ARC_MID moves the same control point, with its own lever ---


def test_dragging_an_arc_mid_moves_its_owning_control_point(ctx):
    ctx.select(Selection(segment=1))
    segment = ctx.network.segments[1]
    handle = next(
        h for h in shape_handles(segment) if h.kind is ShapeHandleKind.ARC_MID
    )
    assert handle.position != segment.control_points[handle.control_index]  # real lever
    lever = handle.position - segment.control_points[handle.control_index]

    tool = ShapeRoadTool()
    assert tool.grab(ctx, handle.position)
    drop = Vec2(-5.0, 65.0)
    tool.drag_to(ctx, drop)
    tool.release(ctx)

    segment = ctx.network.segments[1]
    assert_vec(segment.control_points[handle.control_index], drop - lever)


# -- an ARC_END drags the corner radius, not a point -------------------------


def test_dragging_an_arc_end_changes_the_corner_radius_not_the_points(ctx):
    ctx.select(Selection(segment=1))
    segment = ctx.network.segments[1]
    original_points = tuple(segment.control_points)
    original_radius = segment.corner_radius
    handle = next(
        h for h in shape_handles(segment) if h.kind is ShapeHandleKind.ARC_END
    )
    corner = segment.control_points[1]
    farther = corner + (handle.position - corner).normalized() * 15.0

    tool = ShapeRoadTool()
    assert tool.grab(ctx, handle.position)
    tool.drag_to(ctx, farther)
    tool.release(ctx)

    segment = ctx.network.segments[1]
    assert segment.corner_radius > original_radius  # dragged farther out
    assert tuple(segment.control_points) == original_points
    assert ctx.history.depth == 1


# -- undo, cancel, and endpoint safety ---------------------------------------


def test_undoing_a_reshape_restores_the_road_byte_identically(ctx):
    before = dumps(ctx.network)
    ctx.select(Selection(segment=1))
    segment = ctx.network.segments[1]
    handle = next(
        h for h in shape_handles(segment) if h.kind is ShapeHandleKind.CONTROL
    )

    tool = ShapeRoadTool()
    tool.grab(ctx, handle.position)
    tool.drag_to(ctx, Vec2(-20.0, 25.0))
    tool.release(ctx)

    ctx.undo()
    ctx.network.rebuild_dirty()
    assert dumps(ctx.network) == before


def test_cancelling_a_drag_restores_the_road_and_records_nothing(ctx):
    ctx.select(Selection(segment=1))
    segment = ctx.network.segments[1]
    original = tuple(segment.control_points)
    handle = next(
        h for h in shape_handles(segment) if h.kind is ShapeHandleKind.CONTROL
    )

    tool = ShapeRoadTool()
    tool.grab(ctx, handle.position)
    tool.drag_to(ctx, Vec2(-20.0, 25.0))
    tool.cancel(ctx)

    assert tuple(ctx.network.segments[1].control_points) == original
    assert ctx.history.depth == 0


def test_dragging_cannot_move_the_road_off_its_own_node(ctx):
    ctx.select(Selection(segment=1))
    segment = ctx.network.segments[1]
    node_a_position = ctx.network.nodes[segment.node_a].position
    handle = next(
        h for h in shape_handles(segment) if h.kind is ShapeHandleKind.CONTROL
    )

    tool = ShapeRoadTool()
    tool.grab(ctx, handle.position)
    tool.drag_to(ctx, Vec2(-20.0, 25.0))
    tool.release(ctx)

    assert_vec(ctx.network.segments[1].control_points[0], node_a_position)


# -- Alt: the curve snap, wired through an explicit argument -----------------
#
# `Modifiers.current()` needs a live pygame video system, which a plain test
# run never has - `drag_to`'s `alt` parameter exists precisely so these cases
# never need one. `handle_event` is the only caller allowed to read it live.


def test_dragging_an_arc_end_with_alt_rounds_the_radius(ctx):
    from roadsim import config

    ctx.select(Selection(segment=1))
    segment = ctx.network.segments[1]
    handle = next(
        h for h in shape_handles(segment) if h.kind is ShapeHandleKind.ARC_END
    )
    corner = segment.control_points[1]
    off_rung = corner + (handle.position - corner).normalized() * 13.3  # untidy

    tool = ShapeRoadTool()
    tool.grab(ctx, handle.position)
    tool.drag_to(ctx, off_rung, alt=True)
    tool.release(ctx)

    assert ctx.network.segments[1].corner_radius in config.RADIUS_LADDER


def test_dragging_without_alt_leaves_the_radius_unrounded(ctx):
    from roadsim import config

    ctx.select(Selection(segment=1))
    segment = ctx.network.segments[1]
    handle = next(
        h for h in shape_handles(segment) if h.kind is ShapeHandleKind.ARC_END
    )
    corner = segment.control_points[1]
    off_rung = corner + (handle.position - corner).normalized() * 13.3

    tool = ShapeRoadTool()
    tool.grab(ctx, handle.position)
    tool.drag_to(ctx, off_rung, alt=False)
    tool.release(ctx)

    assert ctx.network.segments[1].corner_radius not in config.RADIUS_LADDER


def test_dragging_with_alt_near_a_junction_snaps_to_the_tangent():
    network = RoadNetwork()
    network.connect(ORIGIN, Vec2(100.0, 0.0), RESIDENTIAL_TWO_WAY)  # the other arm
    seg_a = network.connect(
        ORIGIN, Vec2(-30.0, 80.0), RESIDENTIAL_TWO_WAY, via=[Vec2(-10.0, 40.0)]
    )
    network.rebuild_all()
    ctx = EditorContext(network, Camera(zoom=10.0, viewport=(1440, 900)))
    ctx.select(Selection(segment=seg_a.id))

    handle = next(
        h for h in shape_handles(seg_a) if h.kind is ShapeHandleKind.CONTROL
    )
    tool = ShapeRoadTool()
    tool.grab(ctx, handle.position)
    tool.drag_to(ctx, Vec2(-10.0, 60.0), alt=True)
    tool.release(ctx)

    segment = network.segments[seg_a.id]
    other = next(s for s in network.segments.values() if s.id != segment.id)
    assert_vec(segment.outgoing_dir(True), -other.outgoing_dir(True))


def test_hud_reports_the_active_snap_while_dragging(ctx):
    from roadsim import config

    ctx.select(Selection(segment=1))
    segment = ctx.network.segments[1]
    handle = next(
        h for h in shape_handles(segment) if h.kind is ShapeHandleKind.ARC_END
    )
    corner = segment.control_points[1]
    off_rung = corner + (handle.position - corner).normalized() * 13.3

    tool = ShapeRoadTool()
    tool.grab(ctx, handle.position)
    tool.drag_to(ctx, off_rung, alt=True)

    assert any("snap:" in line for line in tool.hud_lines(ctx))
    tool.release(ctx)
