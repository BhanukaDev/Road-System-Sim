"""Undo.

Every command is held to the same bar: do, undo, and the serialized network is
byte-identical to what it was; redo, and it is byte-identical to the first do.
Comparing *text* rather than object graphs is the point - it catches an id that
changed, a control point that drifted, a profile that came back as a copy.
"""

from __future__ import annotations

import pytest

from roadsim.editor.commands import (
    AddSegment,
    Composite,
    CreateNode,
    History,
    MoveNode,
    NodeSlot,
    RemoveNode,
    RemoveSegment,
    SetProfile,
    SplitSegment,
)
from roadsim.geometry import Vec2
from roadsim.road.network import RoadNetwork
from roadsim.road.presets import ONE_WAY_TWO_LANE, RESIDENTIAL_TWO_WAY, TRAM_AVENUE
from roadsim.serialization import dumps

ORIGIN = Vec2(0.0, 0.0)


@pytest.fixture
def net() -> RoadNetwork:
    """A crossing plus a spur, so commands have junctions to disturb."""
    network = RoadNetwork()
    network.connect(Vec2(-70.0, 0.0), ORIGIN, TRAM_AVENUE)
    network.connect(ORIGIN, Vec2(70.0, 0.0), TRAM_AVENUE)
    network.connect(Vec2(0.0, -70.0), ORIGIN, RESIDENTIAL_TWO_WAY)
    network.connect(ORIGIN, Vec2(0.0, 70.0), RESIDENTIAL_TWO_WAY)
    network.connect(Vec2(70.0, 0.0), Vec2(120.0, 45.0), ONE_WAY_TWO_LANE)
    network.rebuild_all()
    return network


def hub(net: RoadNetwork) -> int:
    return net.node_at(ORIGIN).id


def assert_reversible(net: RoadNetwork, command) -> None:
    """The contract every command signs up to."""
    before = dumps(net)

    command.do(net)
    net.rebuild_dirty()
    after = dumps(net)
    assert after != before, "command changed nothing"

    command.undo(net)
    net.rebuild_dirty()
    assert dumps(net) == before, "undo did not restore the network"

    command.do(net)
    net.rebuild_dirty()
    assert dumps(net) == after, "redo did not reproduce the do"


# -- one test per command -------------------------------------------------


def test_move_node_is_reversible(net):
    assert_reversible(net, MoveNode(hub(net), Vec2(12.0, -8.0)))


def test_create_node_is_reversible(net):
    assert_reversible(net, CreateNode(Vec2(200.0, 200.0)))


def test_remove_node_is_reversible(net):
    """Deleting a junction takes four roads with it. All four must come back."""
    node = hub(net)
    assert len(net.nodes[node].segments) == 4
    assert_reversible(net, RemoveNode(node))


def test_remove_segment_is_reversible(net):
    assert_reversible(net, RemoveSegment(1))


def test_set_profile_is_reversible(net):
    assert_reversible(net, SetProfile(1, ONE_WAY_TWO_LANE))


def test_split_segment_is_reversible(net):
    assert_reversible(net, SplitSegment(5, net.segments[5].path.length / 2.0))


def test_add_segment_is_reversible(net):
    a = CreateNode(Vec2(-120.0, 90.0))
    b = CreateNode(Vec2(-40.0, 140.0))
    assert_reversible(
        net,
        Composite(
            [a, b, AddSegment(a.slot, b.slot, [a.position, b.position], TRAM_AVENUE)],
            label="draw road",
        ),
    )


def test_drawing_onto_a_road_splits_it_in_one_step(net):
    """A T-junction is a split plus an add, and must undo as a single action."""
    target = net.segments[5]
    split = SplitSegment(target.id, target.path.length * 0.4)
    free = CreateNode(Vec2(160.0, -40.0))
    assert_reversible(
        net,
        Composite(
            [split, free, AddSegment(split.slot, free.slot, [ORIGIN, free.position],
                                     RESIDENTIAL_TWO_WAY)],
            label="draw road",
        ),
    )


# -- specific guarantees ---------------------------------------------------


def test_remove_segment_takes_its_orphaned_nodes_with_it(net):
    """The spur's far end belongs to nothing else, so it should not linger."""
    spur = net.segments[5]
    far_end = spur.node_b
    shared = spur.node_a
    RemoveSegment(spur.id).do(net)
    assert far_end not in net.nodes
    assert shared in net.nodes, "a node other roads still use must survive"


def test_remove_segment_keeps_nodes_other_roads_still_use(net):
    RemoveSegment(1).do(net)
    assert hub(net) in net.nodes


def test_redo_reuses_the_same_ids(net):
    """Not merely a network that looks the same - the same one."""
    create = CreateNode(Vec2(200.0, 0.0))
    create.do(net)
    first_id = create.slot.node_id
    create.undo(net)
    create.do(net)
    assert create.slot.node_id == first_id


def test_split_redo_reuses_the_same_ids(net):
    command = SplitSegment(5, net.segments[5].path.length / 2.0)
    command.do(net)
    ids = (command.new_node_id, sorted(net.segments))
    command.undo(net)
    command.do(net)
    assert (command.new_node_id, sorted(net.segments)) == ids


def test_a_composite_that_fails_halfway_leaves_nothing_behind(net):
    """Half an operation is worse than none of it."""
    before = dumps(net)
    good = CreateNode(Vec2(300.0, 300.0))
    doomed = AddSegment(good.slot, NodeSlot(99999), [ORIGIN, ORIGIN], TRAM_AVENUE)
    with pytest.raises(KeyError):
        Composite([good, doomed]).do(net)
    net.rebuild_dirty()
    assert dumps(net) == before


def test_commands_do_not_rebuild_junctions_themselves(net):
    """Rebuilding belongs to the frame loop, once, after the command lands."""
    MoveNode(hub(net), Vec2(20.0, 20.0)).do(net)
    assert net.dirty_nodes, "the command should have left the node dirty"


# -- history ---------------------------------------------------------------


def test_history_undoes_and_redoes_in_order(net):
    history = History(net)
    history.push(MoveNode(hub(net), Vec2(10.0, 0.0)))
    history.push(SetProfile(1, ONE_WAY_TWO_LANE))
    assert history.depth == 2

    history.undo()
    assert net.segments[1].profile is TRAM_AVENUE
    history.undo()
    assert net.nodes[hub(net)].position == ORIGIN
    assert not history.can_undo

    history.redo()
    history.redo()
    assert net.segments[1].profile is ONE_WAY_TWO_LANE


def test_a_new_command_clears_the_redo_stack(net):
    history = History(net)
    history.push(MoveNode(hub(net), Vec2(10.0, 0.0)))
    history.undo()
    assert history.can_redo
    history.push(SetProfile(1, ONE_WAY_TWO_LANE))
    assert not history.can_redo


def test_undoing_the_whole_stack_restores_the_original_file(net):
    before = dumps(net)
    history = History(net)
    history.push(MoveNode(hub(net), Vec2(14.0, -3.0)))
    history.push(SetProfile(3, ONE_WAY_TWO_LANE))
    history.push(RemoveSegment(5))
    history.push(SplitSegment(1, net.segments[1].path.length / 3.0))

    while history.can_undo:
        history.undo()
    net.rebuild_dirty()
    assert dumps(net) == before


def test_history_reports_what_the_next_undo_does(net):
    history = History(net)
    assert history.undo_label is None
    history.push(SetProfile(1, ONE_WAY_TWO_LANE))
    assert history.undo_label == "set profile"
    history.undo()
    assert history.redo_label == "set profile"


def test_history_forgets_beyond_its_limit(net):
    node = hub(net)
    history = History(net, limit=3)
    for i in range(6):
        history.push(MoveNode(node, Vec2(float(i), 0.0)))
    assert history.depth == 3
