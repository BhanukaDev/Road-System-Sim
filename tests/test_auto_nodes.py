"""A long stroke becomes several roads, and a road can be cut by hand (D24).

The invariants: cuts fall only on straights, evenly, never inside a fillet; the
pieces together are exactly the road the stroke would have made as one; every
cut is a straight through-joint of one profile, so nothing about the drawing
changes; and the whole thing is still one undo step.
"""

from __future__ import annotations

import math

import pytest

from roadsim import config
from roadsim.editor.context import EditorContext
from roadsim.editor.tools.draw_road import (
    DrawRoadTool,
    auto_node_stations,
    build_road_command,
    partition_corners,
)
from roadsim.geometry import LineSegment, Vec2, fit_polyline
from roadsim.render.camera import Camera
from roadsim.road.network import RoadNetwork
from roadsim.road.presets import AVENUE_FOUR_LANE, ONE_WAY_TWO_LANE, RESIDENTIAL_TWO_WAY

from .conftest import EXACT, assert_vec

SPACING = config.AUTO_NODE_SPACING


@pytest.fixture
def ctx() -> EditorContext:
    return EditorContext(RoadNetwork(), Camera(zoom=10.0, viewport=(1440, 900)))


def draw(ctx: EditorContext, points: list[Vec2]):
    command = build_road_command(ctx, points, None, None)
    assert not isinstance(command, str), command
    ctx.apply(command)
    ctx.network.rebuild_dirty()
    return command


# -- where the cuts go -----------------------------------------------------------


def test_a_road_shorter_than_two_spacings_is_not_cut(ctx):
    draw(ctx, [Vec2(0.0, 0.0), Vec2(SPACING * 2 - 1.0, 0.0)])
    assert len(ctx.network.segments) == 1
    assert len(ctx.network.nodes) == 2


def test_a_long_straight_is_cut_into_equal_pieces(ctx):
    length = SPACING * 4 + 10.0
    draw(ctx, [Vec2(0.0, 0.0), Vec2(length, 0.0)])
    count = math.floor(length / SPACING)
    assert len(ctx.network.segments) == count
    xs = sorted(node.position.x for node in ctx.network.nodes.values())
    expected = [length * k / count for k in range(count + 1)]
    assert xs == pytest.approx(expected, abs=EXACT)
    for seg in ctx.network.segments.values():
        assert SPACING - EXACT <= seg.length < 2 * SPACING


def test_cuts_never_land_inside_a_fillet():
    points = [Vec2(0.0, 0.0), Vec2(SPACING * 3, 0.0), Vec2(SPACING * 3, SPACING * 3)]
    path = fit_polyline(points, config.DEFAULT_CORNER_RADIUS)
    arcs = [
        (start, start + piece.length)
        for piece, start in zip(path.pieces, path.piece_starts)
        if not isinstance(piece, LineSegment)
    ]
    assert arcs, "the corner should have produced a fillet"
    for s in auto_node_stations(path):
        for lo, hi in arcs:
            assert not (lo - EXACT <= s <= hi + EXACT)


def test_the_corner_stays_whole_inside_one_piece(ctx):
    corner = Vec2(SPACING * 3, 0.0)
    points = [Vec2(0.0, 0.0), corner, Vec2(SPACING * 3, SPACING * 3)]
    draw(ctx, points)
    assert len(ctx.network.segments) > 1
    with_corner = [s for s in ctx.network.segments.values() if len(s.control_points) == 3]
    assert len(with_corner) == 1
    assert_vec(with_corner[0].control_points[1], corner)
    # No node anywhere near the corner: the nearest one is at least a fillet away.
    nearest = min(n.position.distance_to(corner) for n in ctx.network.nodes.values())
    assert nearest > config.DEFAULT_CORNER_RADIUS


def test_the_pieces_are_exactly_the_road_drawn_as_one(ctx):
    far = SPACING * 3
    points = [Vec2(0.0, 0.0), Vec2(far, 0.0), Vec2(far, far), Vec2(50.0, far)]
    whole = fit_polyline(points, config.DEFAULT_CORNER_RADIUS)
    draw(ctx, points)
    assert len(ctx.network.segments) > 1

    # Every piece's two ends sit on the whole path at the stations the cuts
    # were made at, and the pieces' lengths add up to the whole.
    total = 0.0
    for seg in ctx.network.segments.values():
        for end in (seg.path.start.position, seg.path.end.position):
            on_whole = whole.sample(whole.project(end)).position
            assert_vec(on_whole, end)
        total += seg.path.length
    assert total == pytest.approx(whole.length, abs=1e-6)


def test_every_cut_is_a_through_joint_with_no_junction(ctx):
    draw(ctx, [Vec2(0.0, 0.0), Vec2(SPACING * 3, 0.0)])
    interior = [n for n in ctx.network.nodes.values() if n.degree == 2]
    assert len(interior) == 2
    for node in interior:
        assert ctx.network.junctions.get(node.id) is None
    for seg in ctx.network.segments.values():
        assert seg.trim_a == pytest.approx(0.0, abs=EXACT)
        assert seg.trim_b == pytest.approx(0.0, abs=EXACT)


def test_a_cut_road_is_still_one_undo_step(ctx):
    draw(ctx, [Vec2(0.0, 0.0), Vec2(SPACING * 3, 0.0)])
    assert ctx.history.depth == 1
    ctx.undo()
    ctx.network.rebuild_dirty()
    assert not ctx.network.segments
    assert not ctx.network.nodes


def test_partition_hands_each_corner_to_the_piece_holding_its_fillet():
    points = [Vec2(0.0, 0.0), Vec2(100.0, 0.0), Vec2(100.0, 100.0)]
    path = fit_polyline(points, 10.0)
    corner_s = path.project(points[1])
    first, second, third = partition_corners(points, path, [corner_s - 30.0, corner_s + 30.0])
    assert first[0] == points[0] and len(first) == 2
    assert second[1] == points[1] and len(second) == 3
    assert third[-1] == points[-1] and len(third) == 2


# -- cutting by hand -------------------------------------------------------------


def test_ctrl_click_on_a_road_adds_a_node_there(ctx):
    draw(ctx, [Vec2(0.0, 0.0), Vec2(SPACING, 0.0)])  # one piece: too short to cut
    tool = DrawRoadTool()
    assert tool.add_node_at(ctx, Vec2(20.0, 1.5))  # over the carriageway
    ctx.network.rebuild_dirty()
    assert len(ctx.network.segments) == 2
    node = ctx.network.node_at(Vec2(20.0, 0.0))
    assert node is not None and node.degree == 2
    assert ctx.selection.node == node.id
    assert ctx.network.junctions.get(node.id) is None
    assert ctx.history.depth == 2
    ctx.undo()
    ctx.network.rebuild_dirty()
    assert len(ctx.network.segments) == 1


def test_ctrl_click_off_a_road_does_nothing(ctx):
    draw(ctx, [Vec2(0.0, 0.0), Vec2(SPACING, 0.0)])
    assert not DrawRoadTool().add_node_at(ctx, Vec2(20.0, 40.0))
    assert ctx.history.depth == 1


def test_ctrl_click_at_the_very_end_is_refused_with_a_reason(ctx):
    draw(ctx, [Vec2(0.0, 0.0), Vec2(SPACING, 0.0)])
    assert DrawRoadTool().add_node_at(ctx, Vec2(0.3, 0.0))
    assert len(ctx.network.segments) == 1
    assert "too close" in ctx.status


# -- a cut road is still one road to its junctions -------------------------------


def test_a_gore_budget_is_measured_along_the_run_not_the_piece():
    """Cutting the avenue must not make a shallow ramp that resolved on the
    whole avenue fail on a piece of it: the trim budget follows the run of
    through-joints, so the two builds agree."""

    def build(cut: bool) -> bool:
        editor = EditorContext(RoadNetwork(), Camera(zoom=10.0, viewport=(1440, 900)))
        editor.select_profile(AVENUE_FOUR_LANE.name)
        span = SPACING * 2 + 100.0  # long enough to be cut in two
        if cut:
            draw(editor, [Vec2(-span / 2.0, 0.0), Vec2(span / 2.0, 0.0)])
        else:
            editor.network.connect(
                Vec2(-span / 2.0, 0.0), Vec2(span / 2.0, 0.0), AVENUE_FOUR_LANE
            )
            editor.network.rebuild_all()
        assert (len(editor.network.segments) > 1) is cut
        editor.select_profile(ONE_WAY_TWO_LANE.name)
        tool = DrawRoadTool()
        start = tool.place(editor, Vec2(-100.0, -9.0))  # south side of the avenue
        leave = Vec2(4.0, -1.0).normalized()
        corner = start.position + leave * 60.0  # a verge clear of the avenue
        tool.place(editor, corner)  # locks the south-kerb arrangement
        tool.place(editor, corner + Vec2(120.0, 0.0))
        tool._commit(editor)
        assert not tool.points, editor.status  # committed, not refused
        editor.network.rebuild_dirty()
        mid = editor.network.node_at(Vec2(-100.0, 0.0))
        junction = editor.network.junctions.get(mid.id)
        return junction is not None and not junction.is_degenerate

    assert build(cut=False)
    assert build(cut=True)


def test_a_run_ends_at_a_kink_a_profile_change_or_a_crossing(ctx):
    net = ctx.network
    a = net.connect(Vec2(0.0, 0.0), Vec2(100.0, 0.0), RESIDENTIAL_TWO_WAY)
    net.connect(Vec2(100.0, 0.0), Vec2(200.0, 0.0), RESIDENTIAL_TWO_WAY)
    c = net.connect(Vec2(200.0, 0.0), Vec2(300.0, 0.0), AVENUE_FOUR_LANE)
    net.connect(Vec2(-100.0, 0.0), Vec2(-100.0, 100.0), RESIDENTIAL_TWO_WAY)
    net.connect(Vec2(-100.0, 0.0), Vec2(0.0, 0.0), RESIDENTIAL_TWO_WAY)
    net.rebuild_all()
    # From the west end of `a` the run goes east through the joint at x=100
    # and stops where the avenue begins; from its east end it goes west and
    # stops at the T at x=-100.
    assert net.run_length(a, True) == pytest.approx(200.0, abs=EXACT)
    assert net.run_length(a, False) == pytest.approx(200.0, abs=EXACT)
    assert net.run_length(c, False) == pytest.approx(100.0, abs=EXACT)
