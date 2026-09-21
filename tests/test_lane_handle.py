"""Where a node can be grabbed by a lane or by the boundary between two.

The whole module is one formula - `handle.position == node.position +
handle.normal * handle.offset` - so most of what is worth testing is that the
formula ties correctly to state that already has its own tests
(`RoadProfile.lane_center` / `.edges`, `RoadSegment.lane_centerline`), and that
moving a node by a frozen lever lands the grabbed lane exactly where it was
dropped with no flip term anywhere, in either direction, on either end.
"""

from __future__ import annotations

import pytest

from roadsim.geometry import Vec2
from roadsim.road.lane_handle import (
    LaneHandleKind,
    node_lane_handles,
    segment_end_handles,
)
from roadsim.road.network import RoadNetwork
from roadsim.road.presets import ALLEY, AVENUE_FOUR_LANE, RESIDENTIAL_TWO_WAY

from .conftest import assert_vec

ORIGIN = Vec2(0.0, 0.0)
EAST = Vec2(60.0, 0.0)


def _handles(network: RoadNetwork, node_id: int) -> list:
    return list(node_lane_handles(network, node_id))


# -- the formula itself, on a straight road and a curved one ---------------


@pytest.mark.parametrize("at_a", [True, False])
def test_handle_position_is_node_plus_normal_times_offset_straight(at_a):
    net = RoadNetwork()
    seg = net.connect(ORIGIN, EAST, RESIDENTIAL_TWO_WAY)
    node_id = seg.node_a if at_a else seg.node_b
    node = net.nodes[node_id]

    for handle in segment_end_handles(seg, node_id, at_a):
        assert_vec(handle.position, node.position + handle.normal * handle.offset)


@pytest.mark.parametrize("at_a", [True, False])
def test_handle_position_is_node_plus_normal_times_offset_curved(at_a):
    net = RoadNetwork()
    seg = net.connect(
        Vec2(0.0, 0.0), Vec2(60.0, 30.0), RESIDENTIAL_TWO_WAY, via=[Vec2(30.0, 0.0)]
    )
    node_id = seg.node_a if at_a else seg.node_b
    node = net.nodes[node_id]

    for handle in segment_end_handles(seg, node_id, at_a):
        assert_vec(handle.position, node.position + handle.normal * handle.offset)


def test_handle_sits_on_the_untrimmed_end_not_the_trimmed_carriageway_end():
    """A three-arm junction trims every segment. A handle must not move when
    that trim changes, or the lever would shift under a live drag."""
    net = RoadNetwork()
    net.connect(ORIGIN, EAST, RESIDENTIAL_TWO_WAY)
    net.connect(EAST, Vec2(60.0, 60.0), RESIDENTIAL_TWO_WAY)
    net.connect(EAST, Vec2(120.0, 0.0), RESIDENTIAL_TWO_WAY)
    net.rebuild_dirty()

    node_id = net.node_at(EAST).id
    segment = next(seg for seg, at_a in net.segments_at(node_id) if at_a is False)
    assert segment.trim_b > 0.0  # the junction really did eat into this end

    handle = segment_end_handles(segment, node_id, False)[0]
    untrimmed = segment.path.sample(segment.path.length)
    assert_vec(handle.position, untrimmed.position + handle.normal * handle.offset)


# -- lane and edge offsets tie to the profile the same way everywhere else --


def test_lane_handle_sits_on_the_lane_s_own_centerline():
    net = RoadNetwork()
    seg = net.connect(ORIGIN, EAST, RESIDENTIAL_TWO_WAY)

    for handle in segment_end_handles(seg, seg.node_b, False):
        if handle.kind is not LaneHandleKind.LANE:
            continue
        centerline = seg.lane_centerline(handle.index)
        assert_vec(handle.position, centerline.end.position)
        assert handle.offset == pytest.approx(
            seg.profile.lane_center(handle.index), abs=1e-9
        )


def test_edge_handle_offsets_match_profile_edges_exactly():
    net = RoadNetwork()
    seg = net.connect(ORIGIN, EAST, RESIDENTIAL_TWO_WAY)
    profile = seg.profile

    edges = {
        h.index: h.offset
        for h in segment_end_handles(seg, seg.node_b, False)
        if h.kind is LaneHandleKind.EDGE
    }
    assert edges == {i: offset for i, offset in enumerate(profile.edges)}
    assert edges[0] == pytest.approx(profile.extent_left, abs=1e-9)
    assert edges[len(profile.lanes)] == pytest.approx(-profile.extent_right, abs=1e-9)


def test_every_lane_gets_a_handle_not_only_vehicle_lanes():
    """Unlike an `Anchor`, a lane handle has nothing to continue as a road of
    its own, so a sidewalk is as valid a handle to grab as a car lane."""
    net = RoadNetwork()
    seg = net.connect(ORIGIN, EAST, RESIDENTIAL_TWO_WAY)

    lanes = {
        h.index
        for h in segment_end_handles(seg, seg.node_b, False)
        if h.kind is LaneHandleKind.LANE
    }
    assert lanes == set(seg.profile.indices())


# -- moving a node by a frozen lever: rigidity and the no-flip claim --------


def test_moving_along_its_own_tangent_keeps_every_lane_s_offset_exactly():
    """Drag the grabbed lane straight along its own current direction. The
    lever exactly cancels the offset, so the node translates by the same
    delta with no rotation - and every lane's offset from the node, not only
    the grabbed one, stays the same vector, not just the same length."""
    net = RoadNetwork()
    seg = net.connect(ORIGIN, EAST, RESIDENTIAL_TWO_WAY)
    node_id = seg.node_b
    origin = net.nodes[node_id].position

    before = {
        h.index: h
        for h in segment_end_handles(seg, node_id, False)
        if h.kind is LaneHandleKind.LANE
    }
    grab = before[0]
    delta = Vec2(30.0, 0.0)  # along the segment's own (known) tangent
    target = grab.position + delta

    net.move_node(node_id, target - grab.lever)
    assert_vec(net.nodes[node_id].position, origin + delta)

    seg = net.segments[seg.id]
    after = {
        h.index: h
        for h in segment_end_handles(seg, node_id, False)
        if h.kind is LaneHandleKind.LANE
    }
    for index, handle in before.items():
        assert_vec(after[index].normal, handle.normal)
        assert after[index].offset == pytest.approx(handle.offset, abs=1e-9)


def test_moving_by_lever_preserves_every_lane_s_offset_length():
    """A more violent move, that does rotate the tangent. The offset *length*
    from the node - which is all `RoadProfile` promises - must still hold even
    though the offset *direction* now differs."""
    net = RoadNetwork()
    seg = net.connect(ORIGIN, EAST, RESIDENTIAL_TWO_WAY)
    node_id = seg.node_b

    before = {
        h.index: h
        for h in segment_end_handles(seg, node_id, False)
        if h.kind is LaneHandleKind.LANE
    }
    grab = before[0]
    lever = grab.lever

    target = Vec2(90.0, 40.0)  # off-axis: the tangent rotates
    net.move_node(node_id, target - lever)

    seg = net.segments[seg.id]
    node = net.nodes[node_id]
    for index, handle in before.items():
        after_offset = seg.lane_centerline(index).end.position.distance_to(
            node.position
        )
        assert after_offset == pytest.approx(abs(handle.offset), abs=1e-9)


AT_A_COMBOS = [
    (True, True),
    (True, False),
    (False, True),
    (False, False),
]


@pytest.mark.parametrize("grab_at_a,target_at_a", AT_A_COMBOS)
def test_the_lever_lands_the_grabbed_lane_on_the_dropped_target(
    grab_at_a, target_at_a
):
    """The claim the whole feature rests on: grabbing lane `k` of one road and
    dropping it on lane `m` of another puts those two lane centrelines exactly
    together, with no flip term anywhere - true in all four combinations of
    which end of which road is involved.

    A's far end (the one *not* being dragged) stays fixed, so for the result
    to be exact rather than merely close (the frozen-lever residual the design
    accepts for an arbitrary drag - see D18), A is built already sitting at the
    y its dragged node must land on: both roads point the same way, so both
    normals are `(0, 1)`, and landing lane `k` of A on lane `m` of B moves A's
    node to `B.y + target_offset - grab_offset`. Building A there in the first
    place means the move is a pure translation - zero rotation - which is
    exactly the case the design does promise to be exact.
    """
    grab_offset = RESIDENTIAL_TWO_WAY.lane_center(1)
    target_offset = AVENUE_FOUR_LANE.lane_center(4)
    a_y = target_offset - grab_offset  # b_y is 0.0

    net = RoadNetwork()
    # A's far end (not being dragged) is pinned on whichever side keeps the
    # dragged end from ever crossing it - B sits at x in [40, 100], so a fixed
    # end at x = +-200 always leaves the dragged end on its original side, and
    # the segment's own tangent (and so its normal) never flips mid-test. That
    # reversal is a real, separate thing a drag can do to its own road; it is
    # not what this test is about.
    if grab_at_a:
        a_start, a_end = Vec2(-100.0, a_y), Vec2(200.0, a_y)
    else:
        a_start, a_end = Vec2(-200.0, a_y), Vec2(-40.0, a_y)
    b_start, b_end = Vec2(40.0, 0.0), Vec2(100.0, 0.0)
    seg_a = net.connect(a_start, a_end, RESIDENTIAL_TWO_WAY)
    seg_b = net.connect(b_start, b_end, AVENUE_FOUR_LANE)

    a_node_id = seg_a.node_a if grab_at_a else seg_a.node_b
    b_node_id = seg_b.node_a if target_at_a else seg_b.node_b

    grab = next(
        h
        for h in segment_end_handles(seg_a, a_node_id, grab_at_a)
        if h.kind is LaneHandleKind.LANE and h.index == 1
    )
    target = next(
        h
        for h in segment_end_handles(seg_b, b_node_id, target_at_a)
        if h.kind is LaneHandleKind.LANE and h.index == 4
    )
    assert_vec(grab.normal, target.normal)  # both roads point the same way

    net.move_node(a_node_id, target.position - grab.lever)

    seg_a = net.segments[seg_a.id]
    lane_a = seg_a.lane_centerline(1)
    grabbed_end = lane_a.start.position if grab_at_a else lane_a.end.position
    assert_vec(grabbed_end, target.position)


def test_lever_zero_reproduces_the_plain_centre_move():
    """`lever == Vec2(0, 0)` is what today's centre-handle drag already does -
    the new machinery must not change that case at all."""
    net = RoadNetwork()
    seg = net.connect(ORIGIN, EAST, RESIDENTIAL_TWO_WAY)
    target = Vec2(60.0, 25.0)

    net.move_node(seg.node_b, target - Vec2(0.0, 0.0))
    assert_vec(net.nodes[seg.node_b].position, target)


# -- loops: a node meeting the same segment at both ends -------------------


def test_loop_segment_yields_two_distinct_handle_sets():
    net = RoadNetwork()
    node = net.add_node(Vec2(0.0, 0.0))
    net.add_segment(
        node.id,
        node.id,
        [Vec2(0.0, 0.0), Vec2(40.0, 0.0), Vec2(20.0, 40.0), Vec2(0.0, 0.0)],
        ALLEY,
    )

    handles = _handles(net, node.id)
    at_a_true = [h for h in handles if h.at_a]
    at_a_false = [h for h in handles if not h.at_a]

    assert at_a_true and at_a_false
    assert len(at_a_true) == len(at_a_false)
    # Two genuinely different ends of a loop: the normals do not coincide.
    assert not any(
        a.normal.distance_to(b.normal) < 1e-9
        for a in at_a_true
        for b in at_a_false
        if a.index == b.index and a.kind is b.kind
    )


def test_node_lane_handles_gathers_every_end_meeting_a_node():
    net = RoadNetwork()
    net.connect(ORIGIN, EAST, RESIDENTIAL_TWO_WAY)
    net.connect(EAST, Vec2(60.0, 60.0), RESIDENTIAL_TWO_WAY)

    node_id = net.node_at(EAST).id
    handles = _handles(net, node_id)
    # 4 lanes + 5 edges, from each of the two arms.
    assert len(handles) == 2 * (4 + 5)
