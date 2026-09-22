"""Arranging a narrower road across a wider one by where the cursor is (D25).

Two claims, kept apart. The solver (`editor/lane_draw.py`) lists the
arrangements two profiles admit, picks the one nearest a lateral, and turns it
into a datum in the new road's own end frame - exactly. The tool
(`editor/tools/draw_road.py`) is the wiring: the first click across a wider
road records the attachment, the cursor's side while placing the second point
chooses the arrangement, the second click locks it, and the road is built with
the shifted profile - all with no window and no mouse.
"""

from __future__ import annotations

import pytest

from roadsim.editor.context import EditorContext
from roadsim.editor.lane_draw import (
    Attachment,
    arrangements,
    attachment_for,
    choose_arrangement,
    datum_for_arrangement,
    same_width,
)
from roadsim.editor.snapping import Snap, SnapKind
from roadsim.editor.tools.draw_road import DrawRoadTool, build_road_command
from roadsim.geometry import Vec2, fit_polyline
from roadsim.render.camera import Camera
from roadsim.road.network import RoadNetwork
from roadsim.road.presets import ALLEY, AVENUE_FOUR_LANE, RESIDENTIAL_TWO_WAY

from .conftest import EXACT, assert_vec

WIDE, NARROW = AVENUE_FOUR_LANE, RESIDENTIAL_TWO_WAY
ROOM = (WIDE.total_width - NARROW.total_width) / 2.0


@pytest.fixture
def ctx() -> EditorContext:
    """One 4-lane avenue running east from x=40 to x=120, nothing else."""
    network = RoadNetwork()
    network.connect(Vec2(40.0, 0.0), Vec2(120.0, 0.0), WIDE)
    network.rebuild_all()
    editor = EditorContext(network, Camera(zoom=10.0, viewport=(1440, 900)))
    editor.select_profile(NARROW.name)
    return editor


# -- the solver -----------------------------------------------------------------


def test_equal_widths_have_no_arrangements():
    assert same_width(NARROW, NARROW)
    assert arrangements(NARROW, NARROW) == ()
    assert choose_arrangement(NARROW, NARROW, 3.0) is None


def test_the_kerb_hugging_extremes_are_always_offered():
    options = arrangements(WIDE, NARROW)
    assert options[0] == pytest.approx(-ROOM, abs=EXACT)
    assert options[-1] == pytest.approx(ROOM, abs=EXACT)


def test_every_arrangement_puts_a_lane_line_on_a_lane_line_within_the_body():
    for c in arrangements(WIDE, NARROW):
        assert abs(c) <= ROOM + EXACT
        lines = [edge - NARROW.datum + c for edge in NARROW.edges]
        assert any(
            abs(line - wide_line) < EXACT for line in lines for wide_line in WIDE.edges
        )


def test_arrangements_are_symmetric_for_symmetric_profiles():
    options = arrangements(WIDE, NARROW)
    assert options == pytest.approx(tuple(-c for c in reversed(options)), abs=EXACT)


def test_the_cursor_picks_the_nearest_arrangement():
    options = arrangements(WIDE, NARROW)
    assert choose_arrangement(WIDE, NARROW, -100.0) == options[0]
    assert choose_arrangement(WIDE, NARROW, 100.0) == options[-1]
    for c in options:
        assert choose_arrangement(WIDE, NARROW, c + 0.01) == c


def test_the_datum_is_the_arrangement_when_the_road_continues_straight():
    """Leaving along the wide road's own tangent, the target is exactly
    beside the new road's end, so the datum is `c` to the last bit."""
    attachment = Attachment(Vec2(0.0, 0.0), Vec2(0.0, 1.0), WIDE)
    path = fit_polyline([Vec2(0.0, 0.0), Vec2(80.0, 0.0)], 12.0)
    for c in arrangements(WIDE, NARROW):
        assert datum_for_arrangement(path, True, attachment, c) == pytest.approx(c, abs=EXACT)


def test_the_datum_is_zero_when_the_road_leaves_square_on():
    """The target is then straight ahead, not beside: a T centres itself."""
    attachment = Attachment(Vec2(0.0, 0.0), Vec2(0.0, 1.0), WIDE)
    path = fit_polyline([Vec2(0.0, 0.0), Vec2(0.0, -80.0)], 12.0)
    assert datum_for_arrangement(path, True, attachment, -ROOM) == pytest.approx(0.0, abs=EXACT)


def test_the_datum_lands_the_body_centre_over_the_target_laterally():
    attachment = Attachment(Vec2(0.0, 0.0), Vec2(0.0, 1.0), WIDE)
    path = fit_polyline([Vec2(0.0, 0.0), Vec2(80.0, -20.0)], 12.0)
    c = -ROOM
    datum = datum_for_arrangement(path, True, attachment, c)
    frame = path.sample(0.0)
    body_centre = frame.position + frame.normal * datum
    assert (body_centre - attachment.target(c)).dot(frame.normal) == pytest.approx(
        0.0, abs=EXACT
    )


# -- what a snap attaches to -----------------------------------------------------


def test_a_segment_snap_attaches_at_its_station_with_that_roads_frame(ctx):
    road = ctx.network.segments[1]
    snap = Snap(SnapKind.SEGMENT, Vec2(70.0, 0.0), (road.id, 30.0))
    attachment = attachment_for(ctx.network, snap, NARROW)
    assert attachment is not None
    assert_vec(attachment.centre, Vec2(70.0, 0.0))
    assert_vec(attachment.normal, Vec2(0.0, 1.0))
    assert attachment.profile is WIDE


def test_a_node_snap_attaches_with_the_frame_of_a_road_of_another_width(ctx):
    node = ctx.network.node_at(Vec2(40.0, 0.0))
    snap = Snap(SnapKind.NODE, node.position, node.id)
    attachment = attachment_for(ctx.network, snap, NARROW)
    assert attachment is not None
    assert_vec(attachment.centre, node.position)
    assert abs(attachment.normal.dot(Vec2(0.0, 1.0))) == pytest.approx(1.0, abs=EXACT)


def test_nothing_to_attach_to_when_widths_match_or_the_snap_is_free(ctx):
    road = ctx.network.segments[1]
    snap = Snap(SnapKind.SEGMENT, Vec2(70.0, 0.0), (road.id, 30.0))
    assert attachment_for(ctx.network, snap, WIDE) is None
    assert attachment_for(ctx.network, Snap(SnapKind.GRID, Vec2(0.0, 0.0)), NARROW) is None
    assert attachment_for(ctx.network, None, NARROW) is None


# -- the tool -------------------------------------------------------------------


def test_the_first_click_across_a_wider_road_records_the_attachment(ctx):
    tool = DrawRoadTool()
    tool.place(ctx, Vec2(70.0, -6.0))  # over the avenue, south of centre
    assert tool.start_attachment is not None
    assert tool.arrangement is None  # not chosen yet
    assert_vec(tool.points[0], Vec2(70.0, 0.0))  # the road ends on the centreline


def test_the_cursor_side_chooses_the_arrangement_until_the_second_click(ctx):
    node = ctx.network.node_at(Vec2(40.0, 0.0))
    tool = DrawRoadTool()
    tool.place(ctx, node.position)
    below = tool.start_arrangement(ctx, Vec2(0.0, -30.0))
    above = tool.start_arrangement(ctx, Vec2(0.0, 30.0))
    assert below is not None and above is not None
    assert below == -above
    assert abs(below) == pytest.approx(ROOM, abs=EXACT)

    tool.place(ctx, Vec2(-40.0, -30.0))  # locks the side the cursor was on
    assert tool.arrangement == below
    assert tool.start_arrangement(ctx, Vec2(0.0, 30.0)) == below  # no longer live


def test_a_road_continuing_a_wider_road_is_built_hugging_the_chosen_kerb(ctx):
    """The whole claim end to end: continue the avenue westward from its end
    node with the cursor south of it, and the narrow road's right kerb lies
    exactly on the avenue's right kerb - beyond the taper that joins them
    (D26), which is why the road proper starts at a node of its own."""
    node = ctx.network.node_at(Vec2(40.0, 0.0))
    tool = DrawRoadTool()
    tool.place(ctx, node.position)
    tool.place(ctx, Vec2(-40.0, -30.0))  # well south: the kerb-hugging extreme
    tool.points[-1] = Vec2(-40.0, 0.0)  # keep the leave exactly straight
    tool._commit(ctx)
    ctx.network.rebuild_dirty()

    new = next(
        s
        for s in ctx.network.segments.values()
        if s.profile.lanes == NARROW.lanes and not s.is_transition
    )
    assert node.id not in (new.node_a, new.node_b)  # the taper sits between
    frame = new.path.sample(0.0)
    right_kerb = frame.position - frame.normal * new.profile.extent_right
    left_kerb = frame.position + frame.normal * new.profile.extent_left
    kerbs = sorted((right_kerb.y, left_kerb.y))
    assert kerbs[0] == pytest.approx(-WIDE.extent_right, abs=EXACT)
    assert ctx.history.depth == 1


def test_a_road_of_the_same_width_centres_and_keeps_its_name(ctx):
    ctx.select_profile(WIDE.name)
    node = ctx.network.node_at(Vec2(40.0, 0.0))
    tool = DrawRoadTool()
    tool.place(ctx, node.position)
    tool.place(ctx, Vec2(-40.0, -30.0))
    tool._commit(ctx)
    new = next(s for s in ctx.network.segments.values() if s.id != 1)
    assert new.profile.name == WIDE.name
    assert new.profile.datum == pytest.approx(0.0, abs=EXACT)


def test_finishing_across_a_wider_road_arranges_by_where_the_cursor_landed(ctx):
    tool = DrawRoadTool()
    start = tool.place(ctx, Vec2(-40.0, 0.0))  # arriving straight along the avenue
    end = tool.place(ctx, Vec2(70.0, -ROOM))  # over the avenue, south side
    assert end.kind is SnapKind.SEGMENT
    c = tool.end_arrangement(ctx, end, Vec2(70.0, -ROOM))
    assert c == pytest.approx(-ROOM, abs=EXACT)
    command = build_road_command(ctx, list(tool.points), start, end, None, c)
    ctx.apply(command)
    ctx.network.rebuild_dirty()
    # The road stays centred on its own nodes (D28); the arrangement is the
    # datum at the taper's mouth on the avenue.
    road = next(
        s
        for s in ctx.network.segments.values()
        if s.profile.lanes == NARROW.lanes and not s.is_transition
    )
    taper = next(s for s in ctx.network.segments.values() if s.is_transition)
    assert road.profile.datum == pytest.approx(0.0, abs=EXACT)
    assert taper.profile_b.datum == pytest.approx(-ROOM, abs=EXACT)


def test_both_ends_arranged_gives_a_centred_road_placed_by_its_start(ctx):
    """One road, two arrangements: the body sits where the start's
    arrangement puts it and stays centred on its own nodes; each end's taper
    then runs from that body to the road it joins, whatever that road's
    section (D28, keeping the start-wins rule of D25)."""
    ctx.network.connect(Vec2(-120.0, 0.0), Vec2(-40.0, 0.0), ALLEY)  # narrower still
    ctx.network.rebuild_all()
    tool = DrawRoadTool()
    west = ctx.network.node_at(Vec2(-40.0, 0.0))
    east = ctx.network.node_at(Vec2(40.0, 0.0))
    start = Snap(SnapKind.NODE, west.position, west.id)
    end = Snap(SnapKind.NODE, east.position, east.id)
    start_c = tool.end_arrangement(ctx, start, Vec2(-40.0, 3.0))
    end_c = tool.end_arrangement(ctx, end, Vec2(40.0, -30.0))
    assert start_c is not None and end_c is not None
    command = build_road_command(ctx, [west.position, east.position], start, end, start_c, end_c)
    ctx.apply(command)
    ctx.network.rebuild_dirty()
    tapers = sorted(
        (s for s in ctx.network.segments.values() if s.is_transition),
        key=lambda s: s.path.start.position.x,
    )
    assert len(tapers) == 2
    first, last = tapers
    assert first.profile.same_section(ALLEY)  # from the alley's own section ...
    assert first.path.end.position.y == pytest.approx(start_c, abs=EXACT)  # ... to the body
    assert last.profile_b.same_section(WIDE)  # and out to the avenue's
    assert last.profile.datum == pytest.approx(0.0, abs=EXACT)
    road = next(
        s
        for s in ctx.network.segments.values()
        if s.profile.lanes == NARROW.lanes and not s.is_transition
    )
    assert road.profile.datum == pytest.approx(0.0, abs=EXACT)


def test_hovering_a_wider_road_moves_the_footprint_to_the_arranged_body(ctx):
    tool = DrawRoadTool()
    tool._raw = Vec2(70.0, -6.0)
    tool._hover = tool._snap_world(ctx, tool._raw)
    ctx.cursor = tool._hover.position
    preview = tool.preview(ctx)
    assert preview.footprint is not None
    assert preview.footprint.x == pytest.approx(70.0, abs=EXACT)
    assert preview.footprint.y == pytest.approx(-ROOM, abs=EXACT)
    assert preview.handles == []


def test_hovering_open_space_keeps_the_footprint_under_the_cursor(ctx):
    tool = DrawRoadTool()
    tool._raw = Vec2(0.0, 300.0)
    tool._hover = tool._snap_world(ctx, tool._raw)
    ctx.cursor = tool._hover.position
    assert tool.preview(ctx).footprint == ctx.cursor
