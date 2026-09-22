"""Lane lines pair by direction of travel, and a stranded direction turns back (D27).

The pairing used to count outward from the middle of each road, which is
right only when both middles are seams between opposing traffic. A one-way
road has no seam, and an asymmetric road's seam is off-centre. Now each
direction group pairs with the same direction on the other side, seam first;
a direction with no counterpart runs its lines out to the kerb and gets a
U-turn on every lane.

The junction's two ends come out in angular order, so which is `start` and
which is `end` on a marking is not which arm is west: the tests read sides off
the x coordinate instead.
"""

from __future__ import annotations

import pytest

from roadsim import config
from roadsim.editor.context import EditorContext
from roadsim.editor.tools.draw_road import DrawRoadTool
from roadsim.geometry import Vec2
from roadsim.render.camera import Camera
from roadsim.road.decal import get as decal_for
from roadsim.road.lane import LaneType
from roadsim.road.markings import MarkingKind
from roadsim.road.network import RoadNetwork
from roadsim.road.presets import (
    ASYMMETRIC_BOULEVARD,
    AVENUE_FOUR_LANE,
    ONE_WAY_TWO_LANE,
    RESIDENTIAL_TWO_WAY,
)
from roadsim.road.transition import U_TURN, build_taper, build_transition

from .conftest import EXACT

WEST, NODE, EAST = Vec2(-70.0, 0.0), Vec2(0.0, 0.0), Vec2(70.0, 0.0)


def transition(west, east):
    """`west` drawn west -> east into the node, `east` drawn on eastward: a
    one-way placed as `west` flows *into* the node, as `east` flows away."""
    net = RoadNetwork()
    net.connect(WEST, NODE, west)
    net.connect(NODE, EAST, east)
    net.rebuild_all()
    node = net.node_at(NODE).id
    ends = net.segments_at(node)
    return build_transition(net.junctions[node], {(s.id, at_a): s for s, at_a in ends})


def _west_east(marking) -> tuple[float, float]:
    """The y of the marking's point on the west arm, and on the east arm."""
    a, b = marking.start, marking.end
    return (a.y, b.y) if a.x < b.x else (b.y, a.y)


def _kerbs(profile) -> set[float]:
    driving = [k for k, lane in enumerate(profile.lanes) if lane.type.carries_vehicles]
    return {round(profile.edges[min(driving)], 9), round(profile.edges[max(driving) + 1], 9)}


def _median_edges(profile) -> set[float]:
    medians = [k for k, lane in enumerate(profile.lanes) if lane.type is LaneType.MEDIAN]
    return {round(profile.edges[k], 9) for k in medians} | {
        round(profile.edges[k + 1], 9) for k in medians
    }


# -- one-way into two-way ---------------------------------------------------------


def test_the_one_way_roads_seam_kerb_continues_as_the_centre_line():
    """Under drive-on-left the one-way road's lanes all flow east and keep
    left, so they continue the two-way road's *left* lane: the one-way's
    right kerb is where the centre line arrives, not its middle divider."""
    result = transition(ONE_WAY_TWO_LANE, RESIDENTIAL_TWO_WAY)
    centre = [m for m in result.markings if m.kind is MarkingKind.CENTER_LINE]
    assert len(centre) == 1
    west_y, east_y = _west_east(centre[0])
    right_kerb = ONE_WAY_TWO_LANE.edges[max(ONE_WAY_TWO_LANE.forward_lanes) + 1]
    assert west_y == pytest.approx(right_kerb, abs=EXACT)
    assert east_y == pytest.approx(0.0, abs=EXACT)


def test_the_two_way_roads_divider_pairs_with_the_one_ways_divider():
    result = transition(ONE_WAY_TWO_LANE, RESIDENTIAL_TWO_WAY)
    dividers = [m for m in result.markings if m.kind is MarkingKind.LANE_DIVIDER]
    assert len(dividers) == 1
    west_y, east_y = _west_east(dividers[0])
    assert west_y == pytest.approx(0.0, abs=EXACT)  # the one-way divider
    assert round(east_y, 9) in _kerbs(RESIDENTIAL_TWO_WAY)  # runs out at the kerb
    assert dividers[0].is_taper


def test_the_lane_flowing_against_the_one_way_gets_a_u_turn():
    """The two-way road's lane heading west arrives at a road that only flows
    east: it stops here, and every lane of it says turn back."""
    result = transition(ONE_WAY_TWO_LANE, RESIDENTIAL_TWO_WAY)
    u_turns = [a for a in result.arrows if a.decal == U_TURN]
    assert len(u_turns) == len(RESIDENTIAL_TWO_WAY.backward_lanes) == 1
    arrow = u_turns[0]
    lane = RESIDENTIAL_TWO_WAY.backward_lanes[0]
    assert arrow.position.y == pytest.approx(RESIDENTIAL_TWO_WAY.lane_center(lane), abs=EXACT)
    assert arrow.position.x > 0.0  # on the two-way road
    assert arrow.forward.x < 0.0  # pointing at the mouth it cannot pass
    # Eastbound, two one-way lanes become one: that side merges as usual.
    merges = [a for a in result.arrows if a.decal.startswith("arrow_merge")]
    assert len(merges) == 1 and merges[0].position.x < 0.0


def test_a_one_way_flowing_away_strands_nothing():
    """The other way round nobody is blocked: eastbound traffic carries on,
    and the two-way road's westbound lane is merely empty."""
    result = transition(RESIDENTIAL_TWO_WAY, ONE_WAY_TWO_LANE)
    assert not any(a.decal == U_TURN for a in result.arrows)


def test_no_u_turn_when_both_directions_carry_on():
    result = transition(AVENUE_FOUR_LANE, RESIDENTIAL_TWO_WAY)
    assert not any(a.decal == U_TURN for a in result.arrows)


# -- asymmetric roads ---------------------------------------------------------------


def test_median_edges_pair_with_median_edges_not_with_the_body_centre():
    """The boulevard's median is off its body centre. Counting from the
    middle paired its edges a lane apart from the avenue's; counting from the
    seam pairs them edge for edge."""
    result = transition(AVENUE_FOUR_LANE, ASYMMETRIC_BOULEVARD)
    medians = [m for m in result.markings if m.kind is MarkingKind.MEDIAN_EDGE]
    assert len(medians) == 2
    for marking in medians:
        west_y, east_y = _west_east(marking)
        assert round(west_y, 9) in _median_edges(AVENUE_FOUR_LANE)
        assert round(east_y, 9) in _median_edges(ASYMMETRIC_BOULEVARD)
        assert not marking.is_taper


def test_same_direction_lanes_stay_on_their_own_side_of_the_seam():
    """Every line stays on the side of its own road's seam that its
    direction lives on: a forward line pairs with a forward line, whatever
    the lane counts."""
    result = transition(AVENUE_FOUR_LANE, ASYMMETRIC_BOULEVARD)
    seam_west = sum(_median_edges(AVENUE_FOUR_LANE)) / 2.0
    seam_east = sum(_median_edges(ASYMMETRIC_BOULEVARD)) / 2.0
    for marking in result.markings:
        west_y, east_y = _west_east(marking)
        assert (west_y - seam_west) * (east_y - seam_east) >= -EXACT


def test_the_lost_backward_lane_of_the_avenue_tapers_to_the_boulevards_kerb():
    result = transition(AVENUE_FOUR_LANE, ASYMMETRIC_BOULEVARD)
    tapers = [m for m in result.markings if m.is_taper]
    assert tapers
    assert any(round(_west_east(m)[1], 9) in _kerbs(ASYMMETRIC_BOULEVARD) for m in tapers)


# -- the decal, and the taper segment ------------------------------------------------


def test_the_u_turn_decal_exists_and_fits_a_lane():
    decal = decal_for(U_TURN)
    ys = [p.y for ring in decal.rings for p in ring]
    assert max(ys) - min(ys) == pytest.approx(1.0, abs=1e-9)
    assert 0.3 < decal.aspect < 0.9
    assert decal.fitted_length(config.TRANSITION_ARROW_LENGTH, 3.5) <= config.TRANSITION_ARROW_LENGTH


def test_a_taper_from_a_one_way_into_a_two_way_paints_the_u_turn_too():
    """A one-way flowing west into its dead end, continued west as a two-way:
    the two-way's eastbound lane arrives at a road that only flows west."""
    network = RoadNetwork()
    network.connect(Vec2(120.0, 0.0), Vec2(40.0, 0.0), ONE_WAY_TWO_LANE)
    network.rebuild_all()
    ctx = EditorContext(network, Camera(zoom=10.0, viewport=(1440, 900)))
    ctx.select_profile(AVENUE_FOUR_LANE.name)
    tool = DrawRoadTool()
    tool.place(ctx, Vec2(40.0, 0.0))
    tool.place(ctx, Vec2(-60.0, -30.0))
    tool.points[-1] = Vec2(-60.0, 0.0)
    tool._commit(ctx)
    assert not tool.points, ctx.status
    ctx.network.rebuild_dirty()
    taper = next(s for s in ctx.network.segments.values() if s.is_transition)
    paint = build_taper(taper)
    assert paint is not None
    u_turns = [a for a in paint.arrows if a.decal == U_TURN]
    assert len(u_turns) == 2  # both eastbound lanes of the avenue
    assert all(a.forward.x > 0.0 for a in u_turns)
