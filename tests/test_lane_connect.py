"""Connecting two roads by lane (D20): a merge plus a datum.

The datum is computed from the *post-merge* geometry, not a frozen lever, so -
unlike the position-only alignment in `tests/test_lane_handle.py` - this needs
no careful "no rotation" fixture to be exact: the dragged segment's tangent at
the shared node is whatever it turns out to be, and the datum is solved for
that, after the fact.
"""

from __future__ import annotations

import pytest

from roadsim.editor.commands import MergeNodes, SetProfile
from roadsim.editor.lane_connect import connect_by_lane
from roadsim.geometry import Vec2
from roadsim.road.lane_handle import LaneHandleKind, segment_end_handles
from roadsim.road.network import RoadNetwork
from roadsim.road.presets import AVENUE_FOUR_LANE, RESIDENTIAL_TWO_WAY
from roadsim.serialization import dumps

from .conftest import assert_vec


def _handle(segment, node_id, at_a, kind, index):
    return next(
        h
        for h in segment_end_handles(segment, node_id, at_a)
        if h.kind is kind and h.index == index
    )


def test_connect_by_lane_merges_onto_one_shared_node():
    net = RoadNetwork()
    seg_a = net.connect(Vec2(-80.0, 0.0), Vec2(-20.0, 0.0), RESIDENTIAL_TWO_WAY)
    seg_b = net.connect(Vec2(20.0, 0.0), Vec2(80.0, 0.0), AVENUE_FOUR_LANE)
    net.rebuild_all()

    grab = _handle(seg_a, seg_a.node_b, False, LaneHandleKind.LANE, 1)
    drop = _handle(seg_b, seg_b.node_a, True, LaneHandleKind.LANE, 4)

    connect_by_lane(net, grab, drop).do(net)
    net.rebuild_dirty()

    seg_a, seg_b = net.segments[seg_a.id], net.segments[seg_b.id]
    assert seg_a.node_b == seg_b.node_a
    assert grab.node_id not in net.nodes


def test_connect_by_lane_datum_is_computed_from_the_post_merge_geometry():
    """The datum can only be solved for the tangent the dragged segment ends
    up with *after* the merge pins its near end to the target - not whatever
    tangent it happened to have mid-drag. Starting from a very different
    control-point layout must still land on the same answer a road already
    approaching collinearly would.
    """
    net = RoadNetwork()
    # The far leg is steeply angled; only the *final* approach into the
    # shared node needs to be collinear with B for the claim to hold.
    seg_a = net.connect(
        Vec2(-80.0, 40.0), Vec2(-20.0, 0.0), RESIDENTIAL_TWO_WAY, via=[Vec2(-50.0, 0.0)]
    )
    seg_b = net.connect(Vec2(20.0, 0.0), Vec2(80.0, 0.0), AVENUE_FOUR_LANE)
    net.rebuild_all()

    grab = _handle(seg_a, seg_a.node_b, False, LaneHandleKind.LANE, 1)
    drop = _handle(seg_b, seg_b.node_a, True, LaneHandleKind.LANE, 4)

    connect_by_lane(net, grab, drop).do(net)
    net.rebuild_dirty()

    seg_a, seg_b = net.segments[seg_a.id], net.segments[seg_b.id]
    lane_a = seg_a.lane_centerline(1)
    lane_b = seg_b.lane_centerline(4)
    assert_vec(lane_a.end.position, lane_b.start.position)


def test_connect_by_lane_at_a_genuine_angle_still_matches_the_local_offset():
    """A single datum cannot put an arbitrary lane at an arbitrary *world*
    point when the two roads meet at a real angle - only when they are
    collinear does "the chosen lane's own perpendicular offset" and "the
    world point the target lane sits at" coincide. What a datum can always
    do, and does here, is put the chosen lane's own local offset - measured
    in the dragged segment's own frame - exactly on the target's, flipped the
    same way `road/transition.py` already pairs lines at any junction angle.
    This is the honest, always-achievable half of the claim; the exact
    world-position case is the collinear (through-road) one above.
    """
    net = RoadNetwork()
    seg_a = net.connect(Vec2(-80.0, -60.0), Vec2(-20.0, 0.0), RESIDENTIAL_TWO_WAY)
    seg_b = net.connect(Vec2(20.0, 0.0), Vec2(80.0, 0.0), AVENUE_FOUR_LANE)
    net.rebuild_all()

    grab = _handle(seg_a, seg_a.node_b, False, LaneHandleKind.LANE, 1)
    drop = _handle(seg_b, seg_b.node_a, True, LaneHandleKind.LANE, 4)

    connect_by_lane(net, grab, drop).do(net)
    net.rebuild_dirty()

    seg_a, seg_b = net.segments[seg_a.id], net.segments[seg_b.id]
    frame = seg_a.path.sample(seg_a.path.length)
    other_frame = seg_b.path.sample(0.0)
    flip = -1.0 if frame.normal.dot(other_frame.normal) < 0.0 else 1.0
    assert seg_a.profile.lane_center(1) == pytest.approx(flip * drop.offset, abs=1e-9)


def test_connect_by_lane_aligns_an_edge_handle_too():
    net = RoadNetwork()
    seg_a = net.connect(Vec2(-80.0, 0.0), Vec2(-20.0, 0.0), RESIDENTIAL_TWO_WAY)
    seg_b = net.connect(Vec2(20.0, 0.0), Vec2(80.0, 0.0), AVENUE_FOUR_LANE)
    net.rebuild_all()

    grab = _handle(seg_a, seg_a.node_b, False, LaneHandleKind.EDGE, 0)
    drop = _handle(seg_b, seg_b.node_a, True, LaneHandleKind.EDGE, 0)

    connect_by_lane(net, grab, drop).do(net)
    net.rebuild_dirty()

    seg_a, seg_b = net.segments[seg_a.id], net.segments[seg_b.id]
    edge_a = seg_a.path.offset(seg_a.profile.edges[0])
    edge_b = seg_b.path.offset(seg_b.profile.edges[0])
    assert_vec(edge_a.end.position, edge_b.start.position)


AT_A_COMBOS = [(True, True), (True, False), (False, True), (False, False)]


@pytest.mark.parametrize("grab_at_a,drop_at_a", AT_A_COMBOS)
def test_connect_by_lane_aligns_in_all_four_orientations(grab_at_a, drop_at_a):
    """Both roads collinear (the through-road case the datum trick is exact
    for - see the angle test above for why); what varies here is only which
    end of which road is grabbed and dropped, proving no flip term is needed
    in any of the four combinations, the same claim
    `tests/test_lane_handle.py` makes for the position-only alignment."""
    net = RoadNetwork()
    a1, a2 = Vec2(-80.0, 0.0), Vec2(-20.0, 0.0)
    b1, b2 = Vec2(20.0, 0.0), Vec2(80.0, 0.0)
    seg_a = net.connect(a1 if grab_at_a else a2, a2 if grab_at_a else a1, RESIDENTIAL_TWO_WAY)
    seg_b = net.connect(b1 if drop_at_a else b2, b2 if drop_at_a else b1, AVENUE_FOUR_LANE)
    net.rebuild_all()

    a_node = seg_a.node_a if grab_at_a else seg_a.node_b
    b_node = seg_b.node_a if drop_at_a else seg_b.node_b
    grab = _handle(seg_a, a_node, grab_at_a, LaneHandleKind.LANE, 1)
    drop = _handle(seg_b, b_node, drop_at_a, LaneHandleKind.LANE, 4)

    connect_by_lane(net, grab, drop).do(net)
    net.rebuild_dirty()

    seg_a, seg_b = net.segments[seg_a.id], net.segments[seg_b.id]
    lane_a = seg_a.lane_centerline(1)
    lane_b = seg_b.lane_centerline(4)
    a_point = lane_a.start.position if grab_at_a else lane_a.end.position
    b_point = lane_b.start.position if drop_at_a else lane_b.end.position
    assert_vec(a_point, b_point)


def test_connect_by_lane_is_one_reversible_undo_step():
    net = RoadNetwork()
    seg_a = net.connect(Vec2(-80.0, 0.0), Vec2(-20.0, 0.0), RESIDENTIAL_TWO_WAY)
    seg_b = net.connect(Vec2(20.0, 0.0), Vec2(80.0, 0.0), AVENUE_FOUR_LANE)
    net.rebuild_all()
    before = dumps(net)

    grab = _handle(seg_a, seg_a.node_b, False, LaneHandleKind.LANE, 1)
    drop = _handle(seg_b, seg_b.node_a, True, LaneHandleKind.LANE, 4)
    command = connect_by_lane(net, grab, drop)

    command.do(net)
    net.rebuild_dirty()
    after = dumps(net)
    assert after != before

    command.undo(net)
    net.rebuild_dirty()
    assert dumps(net) == before

    command.do(net)
    net.rebuild_dirty()
    assert dumps(net) == after


def test_connect_by_lane_datum_profile_name_does_not_collide():
    """The datum-shifted profile must save and load as itself, not silently
    merge with the unshifted preset under the same name (D-2's lesson)."""
    net = RoadNetwork()
    seg_a = net.connect(Vec2(-80.0, 0.0), Vec2(-20.0, 0.0), RESIDENTIAL_TWO_WAY)
    net.connect(Vec2(100.0, 0.0), Vec2(160.0, 0.0), RESIDENTIAL_TWO_WAY)  # unshifted, same base name
    seg_b = net.connect(Vec2(20.0, 0.0), Vec2(80.0, 0.0), AVENUE_FOUR_LANE)
    net.rebuild_all()

    grab = _handle(seg_a, seg_a.node_b, False, LaneHandleKind.LANE, 1)
    drop = _handle(seg_b, seg_b.node_a, True, LaneHandleKind.LANE, 4)
    connect_by_lane(net, grab, drop).do(net)
    net.rebuild_dirty()

    names = {seg.profile.name: seg.profile for seg in net.segments.values()}
    residential = [p for name, p in names.items() if name.startswith("residential_two_way")]
    assert len(residential) == 2  # the shifted one and the plain one both survive
    assert RESIDENTIAL_TWO_WAY.name in names
    assert names[RESIDENTIAL_TWO_WAY.name].datum == pytest.approx(0.0, abs=1e-9)
