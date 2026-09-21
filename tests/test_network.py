"""Topology: ids, adjacency, splitting and dirty tracking.

These assert structure rather than millimetres - but dirty tracking is asserted
*exactly*, because a node that goes dirty when it should not is how a rebuild
starts costing the whole network.
"""

from __future__ import annotations

import pytest

from roadsim.geometry import Vec2
from roadsim.road.network import RoadNetwork
from roadsim.road.presets import RESIDENTIAL_TWO_WAY, TRAM_AVENUE

from .conftest import approx, assert_vec

P = RESIDENTIAL_TWO_WAY


def straight(net: RoadNetwork, a: Vec2, b: Vec2, profile=P):
    return net.connect(a, b, profile)


def test_add_segment_links_both_nodes():
    net = RoadNetwork()
    seg = straight(net, Vec2(0.0, 0.0), Vec2(50.0, 0.0))
    assert net.nodes[seg.node_a].segments == {seg.id}
    assert net.nodes[seg.node_b].segments == {seg.id}
    assert net.nodes[seg.node_a].is_dead_end


def test_endpoints_snap_onto_their_nodes():
    """The nodes decide where a road ends, not the stroke the user drew."""
    net = RoadNetwork()
    a = net.add_node(Vec2(0.0, 0.0))
    b = net.add_node(Vec2(60.0, 0.0))
    seg = net.add_segment(a.id, b.id, [Vec2(3.0, 4.0), Vec2(55.0, -2.0)], P)
    assert_vec(seg.path.start.position, a.position)
    assert_vec(seg.path.end.position, b.position)


def test_connect_reuses_a_node_at_the_same_point():
    net = RoadNetwork()
    origin = Vec2(0.0, 0.0)
    straight(net, Vec2(-50.0, 0.0), origin)
    straight(net, origin, Vec2(0.0, 50.0))
    assert len(net.nodes) == 3
    assert net.node_at(origin).degree == 2


def test_ids_stay_stable_across_removal():
    net = RoadNetwork()
    first = straight(net, Vec2(0.0, 0.0), Vec2(50.0, 0.0))
    second = straight(net, Vec2(0.0, 30.0), Vec2(50.0, 30.0))
    net.remove_segment(first.id)
    third = straight(net, Vec2(0.0, 60.0), Vec2(50.0, 60.0))
    assert second.id in net.segments
    assert third.id not in (first.id, second.id)


def test_remove_node_removes_its_segments():
    net = RoadNetwork()
    origin = Vec2(0.0, 0.0)
    straight(net, Vec2(-50.0, 0.0), origin)
    straight(net, origin, Vec2(0.0, 50.0))
    hub = net.node_at(origin).id
    net.remove_node(hub)
    assert not net.segments
    assert hub not in net.nodes
    assert all(not n.segments for n in net.nodes.values())


def test_move_node_moves_every_attached_path_end():
    net = RoadNetwork()
    origin = Vec2(0.0, 0.0)
    left = straight(net, Vec2(-50.0, 0.0), origin)
    up = straight(net, origin, Vec2(0.0, 50.0))
    hub = net.node_at(origin).id
    moved = Vec2(8.0, -6.0)
    net.move_node(hub, moved)
    assert_vec(left.path.end.position, moved)
    assert_vec(up.path.start.position, moved)


# -- merging (D20) ---------------------------------------------------------


def test_merge_nodes_repoints_every_touching_segment():
    net = RoadNetwork()
    dragged_end = Vec2(-10.0, 0.0)
    dragged = straight(net, Vec2(-80.0, 0.0), dragged_end)
    target_end = Vec2(10.0, 0.0)
    target = straight(net, target_end, Vec2(80.0, 0.0))
    dragged_id, target_id = net.node_at(dragged_end).id, net.node_at(target_end).id

    net.merge_nodes(dragged_id, target_id)

    assert dragged_id not in net.nodes
    assert dragged.node_b == target_id
    assert target.node_a == target_id
    assert_vec(dragged.path.end.position, target_end)
    assert net.nodes[target_id].segments == {dragged.id, target.id}


def test_merge_nodes_is_a_no_op_on_itself():
    net = RoadNetwork()
    seg = straight(net, Vec2(0.0, 0.0), Vec2(50.0, 0.0))
    before_position = net.nodes[seg.node_a].position
    net.merge_nodes(seg.node_a, seg.node_a)
    assert net.nodes[seg.node_a].position == before_position
    assert seg.node_a in net.nodes


def test_merge_nodes_marks_both_sides_dirty():
    net = RoadNetwork()
    dragged_end = Vec2(-10.0, 0.0)
    dragged = straight(net, Vec2(-80.0, 0.0), dragged_end)
    target_end = Vec2(10.0, 0.0)
    straight(net, target_end, Vec2(80.0, 0.0))
    dragged_id, target_id = net.node_at(dragged_end).id, net.node_at(target_end).id
    net.rebuild_dirty()  # clean slate

    net.merge_nodes(dragged_id, target_id)
    assert net.dirty_nodes == frozenset({dragged.node_a, target_id})


def test_merge_nodes_handles_a_loop_touching_the_dragged_node_at_both_ends():
    """A loop only appears once in a node's own `.segments` set - both its
    ends must still be repointed, or the untouched one dangles onto a node
    this method is about to delete."""
    net = RoadNetwork()
    loop_node = net.add_node(Vec2(0.0, 0.0))
    loop = net.add_segment(
        loop_node.id,
        loop_node.id,
        [Vec2(0.0, 0.0), Vec2(40.0, 0.0), Vec2(20.0, 40.0), Vec2(0.0, 0.0)],
        P,
    )
    target = net.add_node(Vec2(100.0, 100.0))

    net.merge_nodes(loop_node.id, target.id)

    assert loop.node_a == target.id
    assert loop.node_b == target.id
    assert_vec(loop.path.start.position, target.position)
    assert_vec(loop.path.end.position, target.position)


# -- splitting ------------------------------------------------------------


def test_split_leaves_both_halves_joined_at_the_new_node():
    net = RoadNetwork()
    seg = straight(net, Vec2(-60.0, 0.0), Vec2(60.0, 0.0))
    a, b = seg.node_a, seg.node_b
    first, second, mid = net.split_segment(seg.id, seg.path.length / 2.0)

    assert seg.id not in net.segments
    assert net.nodes[mid].segments == {first, second}
    assert (net.segments[first].node_a, net.segments[first].node_b) == (a, mid)
    assert (net.segments[second].node_a, net.segments[second].node_b) == (mid, b)


def test_split_preserves_total_length_within_fitting_tolerance():
    net = RoadNetwork()
    seg = net.connect(
        Vec2(-60.0, 0.0), Vec2(60.0, 40.0), P, via=[Vec2(0.0, -20.0), Vec2(30.0, 30.0)]
    )
    before = seg.path.length
    first, second, _ = net.split_segment(seg.id, before * 0.4)
    after = net.segments[first].path.length + net.segments[second].path.length
    # Each half is refitted from its own corner points, so a fillet the cut
    # lands inside is lost and that stretch straightens. The M2 design accepts
    # that; what it does not accept is the road visibly changing route.
    assert abs(after - before) < before * 0.05


def test_split_keeps_the_profile_and_radius():
    net = RoadNetwork()
    seg = net.connect(Vec2(-60.0, 0.0), Vec2(60.0, 0.0), TRAM_AVENUE, corner_radius=7.0)
    first, second, _ = net.split_segment(seg.id, seg.path.length / 3.0)
    for half in (net.segments[first], net.segments[second]):
        assert half.profile is TRAM_AVENUE
        assert approx(half.corner_radius, 7.0)


def test_split_at_an_end_is_refused():
    net = RoadNetwork()
    seg = straight(net, Vec2(-60.0, 0.0), Vec2(60.0, 0.0))
    with pytest.raises(ValueError):
        net.split_segment(seg.id, 0.0)
    with pytest.raises(ValueError):
        net.split_segment(seg.id, seg.path.length)


# -- dirty tracking -------------------------------------------------------


def test_mutations_mark_exactly_the_touched_nodes():
    net = RoadNetwork()
    seg = straight(net, Vec2(-50.0, 0.0), Vec2(50.0, 0.0))
    far = straight(net, Vec2(0.0, 200.0), Vec2(80.0, 200.0))
    net.rebuild_dirty()
    assert net.dirty_nodes == frozenset()

    net.move_node(seg.node_a, Vec2(-60.0, 10.0))
    assert net.dirty_nodes == frozenset({seg.node_a, seg.node_b})

    net.rebuild_dirty()
    net.set_profile(far.id, TRAM_AVENUE)
    assert net.dirty_nodes == frozenset({far.node_a, far.node_b})


def test_rebuild_clears_the_dirty_set():
    net = RoadNetwork()
    straight(net, Vec2(-50.0, 0.0), Vec2(50.0, 0.0))
    assert net.dirty_nodes
    net.rebuild_dirty()
    assert not net.dirty_nodes


def test_rebuild_drops_junctions_for_deleted_nodes():
    net = RoadNetwork()
    origin = Vec2(0.0, 0.0)
    straight(net, Vec2(-50.0, 20.0), origin)
    straight(net, origin, Vec2(50.0, 20.0))
    hub = net.node_at(origin).id
    net.rebuild_all()
    assert hub in net.junctions

    net.remove_node(hub)
    net.rebuild_dirty()
    assert hub not in net.junctions


def test_claiming_a_taken_id_is_refused():
    net = RoadNetwork()
    node = net.add_node(Vec2(0.0, 0.0))
    with pytest.raises(KeyError):
        net.add_node(Vec2(10.0, 0.0), node_id=node.id)


def test_segments_at_counts_a_loop_from_both_ends():
    net = RoadNetwork()
    hub = net.add_node(Vec2(0.0, 0.0))
    net.add_segment(
        hub.id,
        hub.id,
        [hub.position, Vec2(40.0, 40.0), Vec2(-40.0, 40.0), hub.position],
        P,
    )
    ends = net.segments_at(hub.id)
    assert [at_a for _, at_a in ends] == [True, False]
