"""One edit tool where there were three (D24), and hover/select for every tool.

The press decides: a shape handle of the selected road, then a node, then a
road to select, then nothing. Each drag is still its own class with its own
tests; what is pinned here is the dispatch, and that `Toolbox` gives every
tool a hover highlight and a click-to-select without the tool knowing.
"""

from __future__ import annotations

import pygame
import pytest

from roadsim.editor.context import EditorContext, Selection
from roadsim.editor.handle import HandleKind
from roadsim.editor.highlight import Highlight
from roadsim.editor.pick import pick
from roadsim.editor.toolbox import TOOLS, Toolbox
from roadsim.editor.tools.edit_road import EditTool
from roadsim.geometry import Vec2
from roadsim.render.camera import Camera
from roadsim.road.network import RoadNetwork
from roadsim.road.presets import RESIDENTIAL_TWO_WAY

from .conftest import assert_vec

A_END = Vec2(-60.0, 0.0)
B_END = Vec2(60.0, 0.0)


@pytest.fixture
def ctx() -> EditorContext:
    network = RoadNetwork()
    network.connect(A_END, B_END, RESIDENTIAL_TWO_WAY)
    network.rebuild_all()
    return EditorContext(network, Camera(zoom=10.0, viewport=(1440, 900)))


def test_the_registry_is_draw_edit_profile():
    assert [cls.name for cls in TOOLS] == ["draw", "edit", "profile"]


# -- the press decides -----------------------------------------------------------


def test_pressing_a_node_grabs_it_and_selects_it(ctx):
    tool = EditTool()
    assert tool.press(ctx, A_END)
    assert tool.dragging
    assert ctx.selection.node == ctx.network.node_at(A_END).id


def test_pressing_a_road_selects_it_and_offers_its_shape_handles(ctx):
    tool = EditTool()
    tool.press(ctx, Vec2(10.0, 2.0))  # over the carriageway, off the centreline
    assert not tool.dragging
    assert ctx.selection == Selection(segment=1)
    kinds = {h.kind for h in tool.preview(ctx).handles}
    assert HandleKind.STRAIGHT_MID in kinds


def test_pressing_a_shape_handle_of_the_selected_road_reshapes_it(ctx):
    tool = EditTool()
    tool.press(ctx, Vec2(10.0, 2.0))
    mid = next(h for h in tool.preview(ctx).handles if h.kind is HandleKind.STRAIGHT_MID)
    before = len(ctx.network.segments[1].control_points)

    assert tool.press(ctx, mid.position)
    assert tool.dragging
    tool.shape.drag_to(ctx, mid.position + Vec2(0.0, 15.0))
    tool.release(ctx)

    segment = ctx.network.segments[1]
    assert len(segment.control_points) == before + 1
    assert ctx.history.depth == 1


def test_a_node_drag_through_the_edit_tool_is_one_undo_step(ctx):
    tool = EditTool()
    tool.press(ctx, A_END)
    ctx.cursor = Vec2(-60.0, 30.3)
    tool.move.drag_to(ctx, tool.move._target(ctx))
    tool.release(ctx)
    node = ctx.network.node_at(Vec2(-60.0, 30.0))
    assert node is not None
    assert ctx.history.depth == 1
    assert not tool.dragging


def test_pressing_nothing_clears_the_selection(ctx):
    tool = EditTool()
    tool.press(ctx, Vec2(10.0, 2.0))
    assert not ctx.selection.is_empty
    tool.press(ctx, Vec2(0.0, 400.0))
    assert ctx.selection.is_empty


def test_escape_cancels_a_drag_then_clears_the_selection(ctx):
    tool = EditTool()
    tool.press(ctx, A_END)
    tool.move.drag_to(ctx, Vec2(-40.0, 30.0))
    assert tool.cancel(ctx)
    assert_vec(ctx.network.nodes[ctx.network.node_at(A_END).id].position, A_END)
    assert ctx.history.depth == 0
    assert not ctx.selection.is_empty
    assert tool.cancel(ctx)
    assert ctx.selection.is_empty


# -- hover and select belong to every tool ---------------------------------------


def test_picking_hits_the_whole_carriageway_not_only_the_centreline(ctx):
    half = RESIDENTIAL_TWO_WAY.half_width
    assert pick(ctx, Vec2(10.0, half * 0.9)) == Selection(segment=1)
    assert pick(ctx, Vec2(10.0, half + 5.0)).is_empty
    assert pick(ctx, A_END + Vec2(0.5, 0.0)).node is not None


def test_picking_the_last_metre_of_a_road_off_its_centreline_is_its_node(ctx):
    """Over the carriageway but past the node's own snap reach, right at the
    end of the road: `over_segment` answers with the node, and picking - and
    the hover highlight drawn every frame - must take that answer."""
    node = ctx.network.node_at(A_END)
    at_end = A_END + Vec2(0.4, -4.0)  # 4 m off the centreline, 0.4 m in
    picked = pick(ctx, at_end)
    assert picked == Selection(node=node.id)
    box = Toolbox(ctx)
    ctx.cursor = at_end
    assert box.preview().highlights == [Highlight.node(node.id)]


def test_every_tool_lights_the_road_under_the_cursor(ctx):
    box = Toolbox(ctx)
    for index in range(len(box.tools)):
        box.select(index)
        ctx.cursor = Vec2(10.0, 2.0)
        assert box.preview().highlights == [Highlight.segment(1)], box.active.name
        ctx.cursor = Vec2(0.0, 400.0)
        assert box.preview().highlights == [], box.active.name


def test_a_click_no_tool_wanted_selects_what_it_landed_on(ctx):
    """The profile brush has nothing to paint in open space and says so; the
    toolbox then treats the click as a selection - here, of nothing."""
    box = Toolbox(ctx)
    box.select(2)  # profile brush
    ctx.select(Selection(segment=1))
    event = pygame.event.Event(
        pygame.MOUSEBUTTONDOWN, button=1, pos=ctx.camera.to_screen(Vec2(0.0, 400.0))
    )
    assert box.handle_event(event)
    assert ctx.selection.is_empty
