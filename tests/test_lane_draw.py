"""Drawing a road onto another road's lane (D21).

Two claims, kept apart on purpose. The solver (`editor/lane_draw.py`) answers
"which datum puts my nearest lane on that handle" from a path and a handle
alone, and is exact. The tool (`editor/tools/draw_road.py`) is the wiring:
a lane handle beats every other snap, the road ends at the handle's *node*,
and the profile it is built with is the shifted one - all with no window and
no mouse, the same way `tests/test_tools.py` drives every other tool.
"""

from __future__ import annotations

import pytest

from roadsim.editor.context import EditorContext
from roadsim.editor.handle import HandleKind
from roadsim.editor.lane_draw import datum_for_lane_target, lane_candidates
from roadsim.editor.snapping import SnapKind
from roadsim.editor.tools.draw_road import DrawRoadTool, build_road_command
from roadsim.geometry import Vec2, fit_polyline
from roadsim.render.camera import Camera
from roadsim.road.lane_handle import LaneHandleKind, segment_end_handles
from roadsim.road.network import RoadNetwork
from roadsim.road.presets import AVENUE_FOUR_LANE, RESIDENTIAL_TWO_WAY

from .conftest import assert_vec

RADIUS = 8.0


def _handle(segment, node_id, at_a, kind, index):
    return next(
        h
        for h in segment_end_handles(segment, node_id, at_a)
        if h.kind is kind and h.index == index
    )


@pytest.fixture
def ctx() -> EditorContext:
    """One 4-lane road running east, with nothing else in the world."""
    network = RoadNetwork()
    network.connect(Vec2(40.0, 0.0), Vec2(120.0, 0.0), AVENUE_FOUR_LANE)
    network.rebuild_all()
    editor = EditorContext(network, Camera(zoom=10.0, viewport=(1440, 900)))
    editor.select_profile(RESIDENTIAL_TWO_WAY.name)
    return editor


# -- the solver ---------------------------------------------------------------


def test_candidates_are_exactly_the_handles_a_node_publishes():
    """What you can aim at and what can be matched are one list - otherwise a
    handle could be offered that no datum can ever honour."""
    offsets = set(lane_candidates(RESIDENTIAL_TWO_WAY))
    network = RoadNetwork()
    segment = network.connect(Vec2(0.0, 0.0), Vec2(50.0, 0.0), RESIDENTIAL_TWO_WAY)
    published = {h.offset for h in segment_end_handles(segment, segment.node_a, True)}
    assert offsets == published


def test_datum_puts_the_nearest_lane_exactly_on_the_target():
    """The whole claim, at the model level: after the shift, one of the new
    road's own handles sits on the target handle to the last bit."""
    network = RoadNetwork()
    other = network.connect(Vec2(40.0, 0.0), Vec2(120.0, 0.0), AVENUE_FOUR_LANE)
    network.rebuild_all()
    target = _handle(other, other.node_a, True, LaneHandleKind.LANE, 3)

    path = fit_polyline([Vec2(-40.0, 0.0), target.node_position], RADIUS)
    datum = datum_for_lane_target(RESIDENTIAL_TWO_WAY, path, False, target)
    shifted = RESIDENTIAL_TWO_WAY.with_datum(datum)

    frame = path.sample(path.length)
    landed = [frame.position + frame.normal * o for o in lane_candidates(shifted)]
    assert min(p.distance_to(target.position) for p in landed) == pytest.approx(
        0.0, abs=1e-9
    )


def test_the_lane_it_picks_is_the_one_already_nearest():
    """Nearest, not same-index: the two roads have different lane counts, so
    an index means nothing across them."""
    network = RoadNetwork()
    other = network.connect(Vec2(40.0, 0.0), Vec2(120.0, 0.0), AVENUE_FOUR_LANE)
    network.rebuild_all()
    target = _handle(other, other.node_a, True, LaneHandleKind.LANE, 4)

    path = fit_polyline([Vec2(-40.0, 0.0), target.node_position], RADIUS)
    datum = datum_for_lane_target(RESIDENTIAL_TWO_WAY, path, False, target)

    # Target is left of centre in the new road's own frame (both run east), so
    # the lane that moves onto it must be a left-hand one, not a right-hand.
    frame = path.sample(path.length)
    lateral = (target.position - frame.position).dot(frame.normal)
    chosen = lateral - (datum - RESIDENTIAL_TWO_WAY.datum)
    assert chosen == pytest.approx(
        min(lane_candidates(RESIDENTIAL_TWO_WAY), key=lambda o: abs(o - lateral)),
        abs=1e-9,
    )


@pytest.mark.parametrize("at_a", [True, False])
def test_either_end_of_the_new_road_can_be_the_one_that_joins(at_a):
    network = RoadNetwork()
    other = network.connect(Vec2(40.0, 0.0), Vec2(120.0, 0.0), AVENUE_FOUR_LANE)
    network.rebuild_all()
    target = _handle(other, other.node_a, True, LaneHandleKind.EDGE, 0)

    far = Vec2(-40.0, 0.0)
    points = [target.node_position, far] if at_a else [far, target.node_position]
    path = fit_polyline(points, RADIUS)
    datum = datum_for_lane_target(RESIDENTIAL_TWO_WAY, path, at_a, target)
    shifted = RESIDENTIAL_TWO_WAY.with_datum(datum)

    frame = path.sample(0.0 if at_a else path.length)
    landed = [frame.position + frame.normal * o for o in lane_candidates(shifted)]
    assert min(p.distance_to(target.position) for p in landed) == pytest.approx(
        0.0, abs=1e-9
    )


# -- the tool -----------------------------------------------------------------


def test_a_lane_handle_beats_every_other_snap(ctx):
    segment = ctx.network.segments[1]
    target = _handle(segment, segment.node_a, True, LaneHandleKind.LANE, 4)

    snap = DrawRoadTool()._snap_world(ctx, target.position)
    assert snap.kind is SnapKind.LANE
    assert snap.lane_handle.index == 4


def test_a_lane_snap_lands_the_road_on_the_node_not_the_handle(ctx):
    segment = ctx.network.segments[1]
    target = _handle(segment, segment.node_a, True, LaneHandleKind.LANE, 4)

    snap = DrawRoadTool()._snap_world(ctx, target.position)
    assert_vec(snap.attach_position, ctx.network.nodes[segment.node_a].position)
    assert snap.attach_node_id == segment.node_a


def test_drawing_onto_a_lane_joins_that_node_and_shifts_the_profile(ctx):
    segment = ctx.network.segments[1]
    target = _handle(segment, segment.node_a, True, LaneHandleKind.LANE, 4)
    tool = DrawRoadTool()

    start = tool._snap_world(ctx, Vec2(-60.0, 0.0))
    end = tool._snap_world(ctx, target.position)
    command = build_road_command(
        ctx, [start.attach_position, end.attach_position], start, end
    )
    ctx.apply(command)
    ctx.network.rebuild_dirty()

    new = next(s for s in ctx.network.segments.values() if s.id != segment.id)
    assert new.node_b == segment.node_a  # one shared node, no new one beside it
    assert new.profile.datum != pytest.approx(0.0, abs=1e-9)

    frame = new.path.sample(new.path.length)
    landed = [frame.position + frame.normal * o for o in lane_candidates(new.profile)]
    assert min(p.distance_to(target.position) for p in landed) == pytest.approx(
        0.0, abs=1e-9
    )


def test_drawing_onto_a_lane_is_one_undo_step(ctx):
    segment = ctx.network.segments[1]
    target = _handle(segment, segment.node_a, True, LaneHandleKind.LANE, 4)
    tool = DrawRoadTool()
    start = tool._snap_world(ctx, Vec2(-60.0, 0.0))
    end = tool._snap_world(ctx, target.position)

    before = len(ctx.network.segments)
    ctx.apply(build_road_command(ctx, [start.attach_position, end.attach_position], start, end))
    ctx.network.rebuild_dirty()
    assert len(ctx.network.segments) == before + 1

    ctx.undo()
    ctx.network.rebuild_dirty()
    assert len(ctx.network.segments) == before
    assert ctx.history.depth == 0


def test_a_road_drawn_nowhere_near_a_lane_keeps_the_plain_profile(ctx):
    tool = DrawRoadTool()
    start = tool._snap_world(ctx, Vec2(-200.0, -200.0))
    end = tool._snap_world(ctx, Vec2(-200.0, -120.0))
    ctx.apply(build_road_command(ctx, [start.position, end.position], start, end))

    new = next(s for s in ctx.network.segments.values() if s.id != 1)
    assert new.profile.name == RESIDENTIAL_TWO_WAY.name
    assert new.profile.datum == pytest.approx(0.0, abs=1e-9)


# -- preview ------------------------------------------------------------------


def test_hovering_a_node_offers_its_lane_and_edge_handles(ctx):
    tool = DrawRoadTool()
    ctx.cursor = ctx.network.nodes[ctx.network.segments[1].node_a].position

    kinds = {h.kind for h in tool.preview(ctx).handles}
    assert kinds == {HandleKind.LANE, HandleKind.EDGE}


def test_the_handle_being_aimed_at_is_the_active_one(ctx):
    segment = ctx.network.segments[1]
    target = _handle(segment, segment.node_a, True, LaneHandleKind.LANE, 4)
    tool = DrawRoadTool()
    tool._hover = tool._snap_world(ctx, target.position)
    ctx.cursor = tool._hover.attach_position

    active = [h for h in tool.preview(ctx).handles if h.active]
    assert len(active) == 1
    assert_vec(active[0].position, target.position)


def test_no_handles_far_from_every_node(ctx):
    tool = DrawRoadTool()
    ctx.cursor = Vec2(-500.0, 500.0)
    assert tool.preview(ctx).handles == []
