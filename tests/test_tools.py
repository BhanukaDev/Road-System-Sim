"""Tools, driven without a window.

Tools produce commands and a preview rather than mutating or drawing, which is
exactly what makes this file possible: every case below is the editor's real
code path with no display, no event loop and no mouse.
"""

from __future__ import annotations

import pytest

from roadsim.editor.commands import Composite
from roadsim.editor.context import EditorContext, Selection
from roadsim.editor.snapping import Snap, SnapKind
from roadsim.editor.tools.draw_road import DrawRoadTool, build_road_command
from roadsim.editor.tools.move_node import MoveNodeTool
from roadsim.editor.tools.profile import ProfileTool
from roadsim.editor.tools.select import pick
from roadsim.geometry import Vec2
from roadsim.render.camera import Camera
from roadsim.road.network import RoadNetwork
from roadsim.road.presets import (
    ASYMMETRIC_BOULEVARD,
    ONE_WAY_TWO_LANE,
    RESIDENTIAL_TWO_WAY,
)
from roadsim.serialization import dumps

from .conftest import approx, assert_vec


@pytest.fixture
def ctx() -> EditorContext:
    """One east-west road, and an editor looking at it."""
    network = RoadNetwork()
    network.connect(Vec2(-60.0, 0.0), Vec2(60.0, 0.0), RESIDENTIAL_TWO_WAY)
    network.rebuild_all()
    return EditorContext(network, Camera(zoom=10.0, viewport=(1440, 900)))


def draw(ctx: EditorContext, points: list[Vec2], start=None, end=None):
    """What the draw tool does once the user commits."""
    command = build_road_command(ctx, points, start, end)
    if isinstance(command, str):
        return command
    ctx.apply(command)
    ctx.network.rebuild_dirty()
    return command


# -- drawing ---------------------------------------------------------------


def test_drawing_in_open_space_creates_both_nodes_and_one_road(ctx):
    draw(ctx, [Vec2(-40.0, 60.0), Vec2(40.0, 60.0)])
    assert len(ctx.network.segments) == 2
    assert len(ctx.network.nodes) == 4


def test_drawing_uses_the_active_profile(ctx):
    ctx.profile_index = ctx.profile_names.index(ASYMMETRIC_BOULEVARD.name)
    draw(ctx, [Vec2(-40.0, 60.0), Vec2(40.0, 60.0)])
    assert ctx.network.segments[2].profile is ASYMMETRIC_BOULEVARD


def test_drawing_from_an_existing_node_reuses_it(ctx):
    node = ctx.network.node_at(Vec2(-60.0, 0.0))
    draw(
        ctx,
        [node.position, Vec2(-60.0, 80.0)],
        start=Snap(SnapKind.NODE, node.position, node.id),
    )
    assert len(ctx.network.nodes) == 3
    assert ctx.network.nodes[node.id].degree == 2


def test_drawing_onto_a_road_splits_it_and_forms_a_junction(ctx):
    """This is what a T-junction *is*: one action, one undo."""
    road = ctx.network.segments[1]
    s = road.path.length / 2.0
    hit = Snap(SnapKind.SEGMENT, road.path.sample(s).position, (road.id, s))
    draw(ctx, [hit.position, Vec2(0.0, 80.0)], start=hit)

    assert road.id not in ctx.network.segments
    assert len(ctx.network.segments) == 3  # two halves plus the new spur
    junction = next(iter(ctx.network.junctions.values()))
    assert len(junction.ends) == 3


def test_undoing_a_t_junction_puts_the_original_road_back(ctx):
    before = dumps(ctx.network)
    road = ctx.network.segments[1]
    s = road.path.length * 0.4
    hit = Snap(SnapKind.SEGMENT, road.path.sample(s).position, (road.id, s))
    command = draw(ctx, [hit.position, Vec2(0.0, 80.0)], start=hit)
    assert isinstance(command, Composite)

    ctx.undo()
    ctx.network.rebuild_dirty()
    assert dumps(ctx.network) == before


def test_a_road_ending_where_it_started_is_split_into_a_loop(ctx):
    """A loop back to its own start becomes two road segments sharing a new node."""
    node = ctx.network.node_at(Vec2(-60.0, 0.0))
    snap = Snap(SnapKind.NODE, node.position, node.id)
    long_way = [node.position, Vec2(-120.0, 70.0), Vec2(-20.0, 70.0), node.position]

    command = draw(ctx, long_way, snap, snap)
    assert isinstance(command, Composite)
    assert len(ctx.network.nodes) == 3
    assert len(ctx.network.segments) == 3
    assert any(
        s.node_a == node.id or s.node_b == node.id
        for s in ctx.network.segments.values()
    )

    degenerate = draw(ctx, [node.position, node.position], snap, snap)
    assert isinstance(degenerate, str)
    assert "too short" in degenerate or "same node" in degenerate


def test_a_road_too_short_to_exist_is_refused(ctx):
    assert "too short" in draw(ctx, [Vec2(0.0, 50.0), Vec2(0.0, 50.2)])


def test_both_ends_on_one_road_is_refused_rather_than_corrupting_it(ctx):
    """The first split destroys the segment the second one is aimed at, so the
    tool says so instead of half-building a road."""
    road = ctx.network.segments[1]
    a, b = road.path.length * 0.3, road.path.length * 0.7
    first = Snap(SnapKind.SEGMENT, road.path.sample(a).position, (road.id, a))
    second = Snap(SnapKind.SEGMENT, road.path.sample(b).position, (road.id, b))
    result = draw(
        ctx, [first.position, Vec2(0.0, 40.0), second.position], first, second
    )
    assert "same road" in result
    assert road.id in ctx.network.segments


def test_a_refused_road_changes_nothing(ctx):
    before = dumps(ctx.network)
    draw(ctx, [Vec2(0.0, 50.0), Vec2(0.0, 50.2)])
    assert dumps(ctx.network) == before
    assert not ctx.history.can_undo


def test_preview_reports_the_real_road_length(ctx):
    tool = DrawRoadTool()
    tool.points = [Vec2(-20.0, 50.0)]
    ctx.cursor = Vec2(20.0, 50.0)
    preview = tool.preview(ctx)

    assert len(preview.paths) == 1
    assert preview.profile is ctx.profile
    assert preview.measurement is not None
    assert approx(preview.measurement, 40.0)
    assert preview.angles == []  # neither end touches existing geometry


def test_preview_shows_the_angle_where_a_new_road_meets_an_existing_one(ctx):
    """Perpendicular off an existing road reads as 90, not some map bearing."""
    node = ctx.network.node_at(Vec2(-60.0, 0.0))
    tool = DrawRoadTool()
    tool.points = [node.position]
    tool.start_snap = Snap(SnapKind.NODE, node.position, node.id)
    ctx.cursor = Vec2(-60.0, 40.0)

    preview = tool.preview(ctx)

    assert len(preview.angles) == 1
    assert_vec(preview.angles[0].position, node.position)
    assert approx(preview.angles[0].degrees, 90.0)


def test_preview_shows_the_turn_angle_at_each_interior_corner(ctx):
    tool = DrawRoadTool()
    tool.points = [Vec2(0.0, 50.0), Vec2(40.0, 50.0)]
    ctx.cursor = Vec2(40.0, 90.0)  # a right-angle turn at the second point

    preview = tool.preview(ctx)

    corner = next(a for a in preview.angles if a.position == Vec2(40.0, 50.0))
    assert approx(corner.degrees, 90.0)


def test_preview_carries_a_guide_extending_an_existing_road(ctx):
    tool = DrawRoadTool()
    tool.points = [Vec2(80.0, 0.0)]
    ctx.cursor = Vec2(120.0, 0.001)  # past the east end, dead in line with it

    preview = tool.preview(ctx)

    assert any(g.anchor == Vec2(60.0, 0.0) for g in preview.guides)


def test_a_blocked_preview_carries_its_reason(ctx):
    tool = DrawRoadTool()
    tool.points = [Vec2(0.0, 50.0), Vec2(0.0, 50.2)]  # too short to commit
    tool._commit(ctx)

    preview = tool.preview(ctx)
    assert preview.invalid
    assert preview.reason == "road is too short"


# -- moving ---------------------------------------------------------------


def test_dragging_a_node_leaves_exactly_one_undo_step(ctx):
    tool = MoveNodeTool()
    node = ctx.network.node_at(Vec2(-60.0, 0.0))
    assert tool.grab(ctx, node.position)

    for y in (5.0, 10.0, 15.0, 22.0):
        tool.drag_to(ctx, Vec2(-70.0, y))
    tool.release(ctx)

    assert ctx.history.depth == 1
    assert_vec(ctx.network.nodes[node.id].position, Vec2(-70.0, 22.0))


def test_undoing_a_drag_returns_the_node_to_where_it_started(ctx):
    before = dumps(ctx.network)
    tool = MoveNodeTool()
    node = ctx.network.node_at(Vec2(-60.0, 0.0))
    tool.grab(ctx, node.position)
    tool.drag_to(ctx, Vec2(-90.0, 40.0))
    tool.release(ctx)

    ctx.undo()
    ctx.network.rebuild_dirty()
    assert dumps(ctx.network) == before


def test_a_drag_that_goes_nowhere_records_nothing(ctx):
    tool = MoveNodeTool()
    node = ctx.network.node_at(Vec2(-60.0, 0.0))
    tool.grab(ctx, node.position)
    tool.release(ctx)
    assert ctx.history.depth == 0


def test_cancelling_a_drag_restores_the_node_and_records_nothing(ctx):
    tool = MoveNodeTool()
    node = ctx.network.node_at(Vec2(-60.0, 0.0))
    tool.grab(ctx, node.position)
    tool.drag_to(ctx, Vec2(20.0, 90.0))
    tool.cancel(ctx)
    assert_vec(ctx.network.nodes[node.id].position, Vec2(-60.0, 0.0))
    assert ctx.history.depth == 0


def test_grabbing_empty_space_does_nothing(ctx):
    tool = MoveNodeTool()
    assert not tool.grab(ctx, Vec2(500.0, 500.0))
    assert tool.node_id is None


def test_dragging_a_node_moves_its_road_and_rebuilds_the_junction(ctx):
    road = ctx.network.segments[1]
    s = road.path.length / 2.0
    hit = Snap(SnapKind.SEGMENT, road.path.sample(s).position, (road.id, s))
    draw(ctx, [hit.position, Vec2(0.0, 80.0)], start=hit)
    hub = next(iter(ctx.network.junctions))
    before = ctx.network.junctions[hub].polygon

    tool = MoveNodeTool()
    tool.grab(ctx, ctx.network.nodes[hub].position)
    tool.drag_to(ctx, Vec2(15.0, 12.0))
    tool.release(ctx)
    ctx.network.rebuild_dirty()

    assert ctx.network.junctions[hub].polygon != before


# -- profile and selection -------------------------------------------------


def test_painting_a_profile_changes_the_road_and_selects_it(ctx):
    ctx.profile_index = ctx.profile_names.index(ONE_WAY_TWO_LANE.name)
    assert ProfileTool().paint(ctx, Vec2(0.0, 0.1))
    assert ctx.network.segments[1].profile is ONE_WAY_TWO_LANE
    assert ctx.selection == Selection(segment=1)
    assert ctx.history.depth == 1


def test_painting_the_profile_a_road_already_has_records_nothing(ctx):
    ProfileTool().paint(ctx, Vec2(0.0, 0.1))
    assert ctx.history.depth == 0


def test_painting_open_space_does_nothing(ctx):
    assert not ProfileTool().paint(ctx, Vec2(0.0, 400.0))


def test_picking_finds_a_node_a_road_or_nothing(ctx):
    node = ctx.network.node_at(Vec2(-60.0, 0.0))
    assert pick(ctx, Vec2(-60.0, 0.1)) == Selection(node=node.id)
    assert pick(ctx, Vec2(10.0, 0.1)) == Selection(segment=1)
    assert pick(ctx, Vec2(0.0, 400.0)).is_empty


def test_undo_drops_a_selection_it_deleted(ctx):
    """Selection must not outlive what it points at."""
    draw(ctx, [Vec2(-40.0, 60.0), Vec2(40.0, 60.0)])
    ctx.select(Selection(segment=2))
    ctx.undo()
    assert ctx.selection.is_empty


def test_the_active_profile_cycles_both_ways(ctx):
    first = ctx.profile.name
    ctx.cycle_profile(1)
    assert ctx.profile.name != first
    ctx.cycle_profile(-1)
    assert ctx.profile.name == first


def test_replacing_the_network_clears_the_history(ctx):
    draw(ctx, [Vec2(-40.0, 60.0), Vec2(40.0, 60.0)])
    assert ctx.history.can_undo
    ctx.replace_network(RoadNetwork())
    assert not ctx.history.can_undo
    assert ctx.selection.is_empty
    assert ctx.snapper.network is ctx.network
