"""A lane change is its own straight segment between two nodes (D26).

Continuing a road of another width from its dead end no longer meets it at a
single node whose junction fakes the width change over half a road-width.
The draw tool puts down a *taper*: a straight segment that carries one section
at its A end and another at its B end, of a length the width difference sets,
and the road proper starts at a real node beyond it. Both roads are full size
at their own node, each joint is a through joint, and the whole thing is one
undo step. Where the stroke branches off a road rather than continuing it -
mid-road, or at a junction - no taper is owed and the junction resolves it.
"""

from __future__ import annotations

import pytest

from roadsim import config
from roadsim.editor.context import EditorContext
from roadsim.editor.tools.draw_road import DrawRoadTool, build_road_command
from roadsim.editor.tools.profile import ProfileTool
from roadsim.geometry import Vec2
from roadsim.render.camera import Camera
from roadsim.road.junction import sections_run_through
from roadsim.road.network import RoadNetwork
from roadsim.road.presets import (
    ASYMMETRIC_BOULEVARD,
    AVENUE_FOUR_LANE,
    RESIDENTIAL_TWO_WAY,
)
from roadsim.road.shape_handle import shape_handles
from roadsim.road.transition import build_taper, carriageway_extents
from roadsim.serialization import dumps, loads

from .conftest import EXACT, assert_vec

WIDE, NARROW = AVENUE_FOUR_LANE, RESIDENTIAL_TWO_WAY
ROOM = (WIDE.total_width - NARROW.total_width) / 2.0
TAPER = config.TRANSITION_TAPER_RATE * (WIDE.total_width - NARROW.total_width)


@pytest.fixture
def ctx() -> EditorContext:
    """One 4-lane avenue running east from x=40 to x=120, nothing else."""
    network = RoadNetwork()
    network.connect(Vec2(40.0, 0.0), Vec2(120.0, 0.0), WIDE)
    network.rebuild_all()
    editor = EditorContext(network, Camera(zoom=10.0, viewport=(1440, 900)))
    editor.select_profile(NARROW.name)
    return editor


def continue_west(ctx: EditorContext, far: Vec2 = Vec2(-80.0, 0.0)):
    """Draw the narrow road on from the avenue's west dead end, hugging its
    south kerb, and hand back (taper, narrow road)."""
    node = ctx.network.node_at(Vec2(40.0, 0.0))
    tool = DrawRoadTool()
    tool.place(ctx, node.position)
    tool.place(ctx, Vec2(-40.0, -30.0))  # south of the avenue: the near kerb
    tool.points[-1] = far  # and dead straight west
    tool._commit(ctx)
    assert not tool.points, ctx.status
    ctx.network.rebuild_dirty()
    tapers = [s for s in ctx.network.segments.values() if s.is_transition]
    roads = [
        s
        for s in ctx.network.segments.values()
        if not s.is_transition and s.profile.lanes == NARROW.lanes
    ]
    assert len(tapers) == 1 and len(roads) == 1
    return tapers[0], roads[0]


# -- what gets built ---------------------------------------------------------------


def test_continuing_a_wider_dead_end_puts_a_taper_before_the_road(ctx):
    taper, road = continue_west(ctx)
    assert len(ctx.network.segments) == 3
    assert len(taper.control_points) == 2
    node_w = ctx.network.node_at(Vec2(40.0, 0.0))
    # The road's first node sits on the road's own centre (D28): a taper's
    # length west, and the arrangement's offset south.
    node_n = ctx.network.node_at(Vec2(40.0 - TAPER, -ROOM))
    assert node_n is not None
    assert {taper.node_a, taper.node_b} == {node_w.id, node_n.id}
    assert node_n.id in (road.node_a, road.node_b)
    assert ctx.history.depth == 1


def test_the_taper_runs_from_the_wide_section_to_the_narrow_one(ctx):
    """Stored in the taper's own A -> B direction: the avenue's A end is at
    the join and the taper heads away from it, so it reads the avenue's
    section mirrored, then hands over to exactly the narrow road's profile."""
    taper, road = continue_west(ctx)
    assert taper.profile.same_section(WIDE.mirrored())
    assert taper.profile_b == road.profile
    assert taper.profile_at(True) is taper.profile
    assert taper.profile_at(False) is taper.profile_b


def test_both_roads_are_full_size_at_their_own_node_and_untrimmed(ctx):
    taper, road = continue_west(ctx)
    avenue = ctx.network.segments[1]
    for node_id in (taper.node_a, taper.node_b):
        assert ctx.network.junctions.get(node_id) is None  # through joints
    assert avenue.trim_a == pytest.approx(0.0, abs=EXACT)
    assert taper.trim_a == taper.trim_b == pytest.approx(0.0, abs=EXACT)
    assert road.trim_a == pytest.approx(0.0, abs=EXACT)
    assert road.trim_b == pytest.approx(0.0, abs=EXACT)


def test_the_narrow_road_hugs_the_chosen_kerb_beyond_the_taper(ctx):
    _, road = continue_west(ctx)
    frame = road.path.sample(0.0)
    kerbs = sorted(
        (
            (frame.position + frame.normal * road.profile.extent_left).y,
            (frame.position - frame.normal * road.profile.extent_right).y,
        )
    )
    assert kerbs[0] == pytest.approx(-WIDE.extent_right, abs=EXACT)


def test_the_whole_thing_is_one_undo_step(ctx):
    continue_west(ctx)
    ctx.undo()
    ctx.network.rebuild_dirty()
    assert set(ctx.network.segments) == {1}
    assert len(ctx.network.nodes) == 2


def test_equal_widths_owe_no_taper(ctx):
    ctx.select_profile(WIDE.name)
    node = ctx.network.node_at(Vec2(40.0, 0.0))
    tool = DrawRoadTool()
    tool.place(ctx, node.position)
    tool.place(ctx, Vec2(-40.0, 0.0))
    tool._commit(ctx)
    assert len(ctx.network.segments) == 2
    assert not any(s.is_transition for s in ctx.network.segments.values())


def test_branching_off_mid_road_owes_no_width_change(ctx):
    """A ramp leaving a road is not a width change of that road: the split
    node is a crossing and the gore resolves it (D25). What it does get is a
    slide - the same section at both ends - to bring its nodes onto its own
    centre (D28)."""
    tool = DrawRoadTool()
    tool.place(ctx, Vec2(80.0, -8.0))
    tool.place(ctx, Vec2(140.0, -40.0))
    tool._commit(ctx)
    assert not tool.points, ctx.status
    tapers = [s for s in ctx.network.segments.values() if s.is_transition]
    assert len(tapers) == 1
    assert tapers[0].profile.lanes == tapers[0].profile_b.lanes
    assert tapers[0].profile.datum != pytest.approx(0.0, abs=EXACT)
    assert tapers[0].profile_b.datum == pytest.approx(0.0, abs=EXACT)


def test_a_slide_hands_the_road_its_own_centre(ctx):
    """The point of D28: beyond the slide the road is centred on its nodes,
    and the far node is where the body ends, not where the drawn line does."""
    tool = DrawRoadTool()
    tool.place(ctx, Vec2(80.0, -8.0))
    tool.place(ctx, Vec2(200.0, -60.0))  # shallow: arranged to the south lanes
    tool._commit(ctx)
    assert not tool.points, ctx.status
    ctx.network.rebuild_dirty()
    road = max(
        (s for s in ctx.network.segments.values() if not s.is_transition), key=lambda s: s.id
    )
    assert road.profile.datum == pytest.approx(0.0, abs=EXACT)
    far = ctx.network.nodes[road.node_b]
    assert far.position.distance_to(Vec2(200.0, -60.0)) > 1.0  # offset with the body


def test_a_road_leaving_square_on_has_nothing_to_arrange_and_no_taper(ctx):
    tool = DrawRoadTool()
    tool.place(ctx, Vec2(80.0, -8.0))
    tool.place(ctx, Vec2(80.0, -120.0))
    tool._commit(ctx)
    assert not tool.points, ctx.status
    assert not any(s.is_transition for s in ctx.network.segments.values())
    assert len(ctx.network.segments) == 3


def test_a_bend_right_after_the_dead_end_is_refused_with_a_reason(ctx):
    """Continuing the avenue, but bending within a few metres of its end:
    a taper is owed and there is no straight to put it on."""
    node = ctx.network.node_at(Vec2(40.0, 0.0))
    tool = DrawRoadTool()
    tool.place(ctx, node.position)
    tool.place(ctx, Vec2(34.0, -2.0))  # carries on west, then bends at once
    tool.place(ctx, Vec2(-40.0, -40.0))
    tool._commit(ctx)
    assert tool.points  # refused, points kept
    assert "lane change" in ctx.status


def test_leaving_a_dead_end_at_a_sharp_angle_is_a_turn_not_a_lane_change(ctx):
    """A narrower road turning off the avenue's end at 60 degrees does not
    continue it: no taper, a plain two-arm junction of the two sections."""
    node = ctx.network.node_at(Vec2(40.0, 0.0))
    tool = DrawRoadTool()
    tool.place(ctx, node.position)
    tool.place(ctx, Vec2(40.0 - 40.0, -70.0))
    tool._commit(ctx)
    assert not tool.points, ctx.status
    ctx.network.rebuild_dirty()
    tapers = [s for s in ctx.network.segments.values() if s.is_transition]
    # A slide to centre the road is fine; a width change is not owed here.
    assert all(t.profile.lanes == t.profile_b.lanes for t in tapers)
    assert ctx.network.junctions.get(node.id) is not None


def test_finishing_on_a_wider_dead_end_tapers_at_that_end(ctx):
    tool = DrawRoadTool()
    tool.place(ctx, Vec2(-80.0, 0.0))
    node = ctx.network.node_at(Vec2(40.0, 0.0))
    tool.place(ctx, node.position + Vec2(0.0, -1.0))  # south side, snaps to the node
    tool._commit(ctx)
    assert not tool.points, ctx.status
    taper = next(s for s in ctx.network.segments.values() if s.is_transition)
    # Heading east into the avenue's A end: its section reads forwards.
    assert taper.profile_b.same_section(WIDE)
    assert taper.profile.lanes == NARROW.lanes
    assert taper.node_b == node.id


def test_a_road_shorter_than_its_taper_is_all_taper(ctx):
    node = ctx.network.node_at(Vec2(40.0, 0.0))
    tool = DrawRoadTool()
    tool.place(ctx, node.position)
    tool.place(ctx, Vec2(40.0 - TAPER / 2.0, 0.0))
    tool._commit(ctx)
    assert not tool.points, ctx.status
    assert len(ctx.network.segments) == 2
    taper = next(s for s in ctx.network.segments.values() if s.is_transition)
    # Half a taper long *along the avenue*; its chord is skewed by the offset.
    along = (taper.path.end.position - taper.path.start.position).dot(Vec2(-1.0, 0.0))
    assert along == pytest.approx(TAPER / 2.0, abs=EXACT)


# -- what a taper is ---------------------------------------------------------------


def test_a_taper_must_be_straight(ctx):
    with pytest.raises(ValueError, match="straight"):
        ctx.network.add_segment(
            1, 2, [Vec2(40.0, 0.0), Vec2(80.0, 20.0), Vec2(120.0, 0.0)], WIDE, profile_b=NARROW
        )


def test_a_taper_has_no_shape_handles_and_cannot_be_split_or_repainted(ctx):
    taper, _ = continue_west(ctx)
    assert shape_handles(taper) == ()
    with pytest.raises(ValueError, match="lane change"):
        ctx.network.split_segment(taper.id, taper.length / 2.0)
    depth = ctx.history.depth
    ctx.select_profile(WIDE.name)
    mid = taper.path.sample(taper.length / 2.0).position
    assert ProfileTool().paint(ctx, mid)
    assert ctx.history.depth == depth
    assert "lane change" in ctx.status
    assert isinstance(
        build_road_command(
            ctx,
            [mid, mid + Vec2(0.0, -60.0)],
            ctx.snapper.over_segment(mid),
            None,
        ),
        str,
    )


def test_a_taper_carries_lane_lines_from_one_section_to_the_other(ctx):
    taper, _ = continue_west(ctx)
    paint = build_taper(taper)
    assert paint is not None and paint.markings
    # The mouths face the roads either side (D28), not the skewed chord.
    frame_a, frame_b = taper.end_frame(True), taper.end_frame(False)
    assert frame_a.tangent.dot(Vec2(-1.0, 0.0)) == pytest.approx(1.0, abs=EXACT)
    assert frame_b.tangent.dot(Vec2(-1.0, 0.0)) == pytest.approx(1.0, abs=EXACT)
    for marking in paint.markings:
        assert abs((marking.start - frame_a.position).dot(frame_a.tangent)) < 1e-6
        assert abs((marking.end - frame_b.position).dot(frame_b.tangent)) < 1e-6


def test_carriageway_extents_are_the_vehicle_kerbs():
    left, right = carriageway_extents(WIDE)
    lanes = [k for k, lane in enumerate(WIDE.lanes) if lane.type.carries_vehicles]
    assert left == WIDE.edges[min(lanes)]
    assert right == WIDE.edges[max(lanes) + 1]


# -- saving --------------------------------------------------------------------------


def test_a_taper_survives_a_save_and_load_byte_for_byte(ctx):
    taper, _ = continue_west(ctx)
    text = dumps(ctx.network)
    loaded = loads(text)
    twin = loaded.segments[taper.id]
    assert twin.is_transition
    assert twin.profile == taper.profile
    assert twin.profile_b == taper.profile_b
    assert dumps(loaded) == text


def test_a_version_one_file_still_loads(ctx):
    import json

    payload = json.loads(dumps(ctx.network))
    payload["version"] = 1
    for seg in payload["segments"]:
        seg.pop("profile_b", None)
    loaded = loads(json.dumps(payload))
    assert set(loaded.segments) == set(ctx.network.segments)


# -- what a through joint is, now ------------------------------------------------------


def test_symmetric_roads_run_through_whichever_way_they_were_drawn():
    net = RoadNetwork()
    a = net.connect(Vec2(0.0, 0.0), Vec2(60.0, 0.0), RESIDENTIAL_TWO_WAY)
    b = net.connect(Vec2(120.0, 0.0), Vec2(60.0, 0.0), RESIDENTIAL_TWO_WAY)  # head to head
    net.rebuild_all()
    assert sections_run_through(a, False, b, False)
    assert net.junctions.get(a.node_b) is None


def test_an_asymmetric_road_joined_head_to_head_is_a_lane_change_not_a_joint():
    net = RoadNetwork()
    a = net.connect(Vec2(0.0, 0.0), Vec2(60.0, 0.0), ASYMMETRIC_BOULEVARD)
    b = net.connect(Vec2(120.0, 0.0), Vec2(60.0, 0.0), ASYMMETRIC_BOULEVARD)
    net.rebuild_all()
    assert not sections_run_through(a, False, b, False)
    assert net.junctions.get(a.node_b) is not None
    c = net.connect(Vec2(60.0, 0.0), Vec2(120.0, 60.0), ASYMMETRIC_BOULEVARD)
    assert sections_run_through(a, False, c, True)


def test_the_ghost_of_a_taper_is_valid(ctx):
    node = ctx.network.node_at(Vec2(40.0, 0.0))
    tool = DrawRoadTool()
    tool.place(ctx, node.position)
    # What a motion event does: the cursor is south of the avenue, over open
    # ground, and the road would end on the grid point beside it.
    tool._raw = Vec2(-40.0, -30.0)
    tool._hover = None
    ctx.cursor = Vec2(-40.0, 0.0)
    preview = tool.preview(ctx)
    assert preview.ghost is not None
    assert not preview.invalid, preview.reason
    assert any(s.is_transition for s in preview.ghost.network.segments.values())
