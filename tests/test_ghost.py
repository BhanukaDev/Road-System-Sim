"""`editor/ghost.py` and `RoadNetwork.copy`: the network one command ahead.

The property that matters is that the ghost is *the same network the commit
will produce* - same ids, same junctions, same trims - and that producing it
leaves the real one untouched.
"""

from __future__ import annotations

import pytest

from roadsim.editor.commands import AddSegment, CreateNode, NodeSlot
from roadsim.editor.context import EditorContext
from roadsim.editor.ghost import ghost_of
from roadsim.editor.snapping import Snap, SnapKind
from roadsim.editor.tools.draw_road import build_road_command
from roadsim.geometry import Vec2
from roadsim.render.camera import Camera
from roadsim.road.network import RoadNetwork
from roadsim.road.presets import RESIDENTIAL_TWO_WAY
from roadsim.serialization import dumps


@pytest.fixture
def ctx() -> EditorContext:
    network = RoadNetwork()
    network.connect(Vec2(-60.0, 0.0), Vec2(60.0, 0.0), RESIDENTIAL_TWO_WAY)
    network.rebuild_all()
    return EditorContext(network, Camera(zoom=10.0, viewport=(1440, 900)))


def _spur_onto_road(ctx: EditorContext):
    road = ctx.network.segments[1]
    s = road.path.length / 2.0
    hit = Snap(SnapKind.SEGMENT, road.path.sample(s).position, (road.id, s))
    return build_road_command(ctx, [hit.position, Vec2(0.0, 60.0)], hit, None)


# -- copy ----------------------------------------------------------------------


def test_a_copy_is_independent_of_its_original(ctx):
    before = dumps(ctx.network)
    clone = ctx.network.copy()
    clone.connect(Vec2(0.0, 40.0), Vec2(40.0, 40.0), RESIDENTIAL_TWO_WAY)
    clone.move_node(1, Vec2(-90.0, 0.0))
    clone.rebuild_all()
    assert dumps(ctx.network) == before


def test_a_copy_allocates_the_same_next_ids(ctx):
    clone = ctx.network.copy()
    ghost_node = clone.add_node(Vec2(0.0, 40.0))
    real_node = ctx.network.add_node(Vec2(0.0, 40.0))
    assert ghost_node.id == real_node.id


def test_a_copy_shares_profiles_rather_than_duplicating_them(ctx):
    clone = ctx.network.copy()
    assert clone.segments[1].profile is ctx.network.segments[1].profile


# -- ghost ---------------------------------------------------------------------


def test_a_ghost_leaves_the_real_network_untouched(ctx):
    before = dumps(ctx.network)
    ghost_of(ctx.network, _spur_onto_road(ctx))
    assert dumps(ctx.network) == before
    assert not ctx.network.dirty_nodes


def test_a_ghost_shows_the_junction_the_commit_will_form(ctx):
    ghost = ghost_of(ctx.network, _spur_onto_road(ctx))
    junctions = [ghost.network.junctions[n] for n in ghost.nodes if n in ghost.network.junctions]
    assert len(junctions) == 1
    assert len(junctions[0].ends) == 3
    # The split halves are re-trimmed, the spur is new: all three are drawn.
    assert len(ghost.segments) == 3
    assert len(ghost.new_segments) == 3  # the two halves are new ids too
    assert not ghost.invalid


def test_a_ghost_matches_the_commit_exactly(ctx):
    ghost = ghost_of(ctx.network, _spur_onto_road(ctx))
    ctx.apply(_spur_onto_road(ctx))
    ctx.network.rebuild_dirty()
    assert dumps(ghost.network) == dumps(ctx.network)


def test_a_ghost_road_through_another_is_invalid_where_it_crosses(ctx):
    command = build_road_command(
        ctx, [Vec2(10.0, -40.0), Vec2(10.0, 40.0)], None, None
    )
    ghost = ghost_of(ctx.network, command)
    assert ghost.invalid
    assert "crosses" in ghost.reason
    assert ghost.problem.position.distance_to(Vec2(10.0, 0.0)) < 1e-6


def test_a_ghost_in_open_space_is_valid_and_capped(ctx):
    a, b = CreateNode(Vec2(0.0, 40.0)), CreateNode(Vec2(40.0, 40.0))
    from roadsim.editor.commands import Composite

    command = Composite(
        [a, b, AddSegment(a.slot, b.slot, [a.position, b.position], RESIDENTIAL_TWO_WAY)]
    )
    ghost = ghost_of(ctx.network, command)
    assert not ghost.invalid
    assert len(ghost.new_segments) == 1
    assert all(n in ghost.network.caps for n in ghost.nodes)


def test_a_ghost_does_not_blame_a_change_for_an_existing_problem(ctx):
    """A broken road elsewhere must not turn every preview red."""
    ctx.network.connect(Vec2(10.0, -40.0), Vec2(10.0, 40.0), RESIDENTIAL_TWO_WAY)
    ctx.network.rebuild_all()
    a, b = CreateNode(Vec2(0.0, 80.0)), CreateNode(Vec2(40.0, 80.0))
    from roadsim.editor.commands import Composite

    command = Composite(
        [a, b, AddSegment(a.slot, b.slot, [a.position, b.position], RESIDENTIAL_TWO_WAY)]
    )
    assert not ghost_of(ctx.network, command).invalid


def test_a_slot_resolved_on_the_ghost_does_not_leak_into_a_fresh_command(ctx):
    slot = NodeSlot()
    ghost_of(ctx.network, CreateNode(Vec2(0.0, 40.0), slot))
    assert slot.node_id is not None  # the ghost resolved it, as a real do would
    # ...which is exactly why the tool builds a fresh command for the commit.
