"""Markings carried across a lane-count transition.

The case this exists for is a 2-lane road meeting a 4-lane one: a real
junction, already drawn as a transition patch, that used to come out as bare
asphalt because per-segment markings stop dead at each mouth.

Nothing here asserts anything about *connectivity*. The pairing is geometric,
for paint only - D5 reserves lane-to-lane connections for M4/M5, and a test
that read intent into these lines would be the thing that quietly turns this
module into that model.
"""

from __future__ import annotations

import pytest

from roadsim.geometry import Vec2
from roadsim.road.markings import MarkingKind
from roadsim.road.network import RoadNetwork
from roadsim.road.presets import (
    AVENUE_FOUR_LANE,
    ONE_WAY_TWO_LANE,
    RESIDENTIAL_TWO_WAY,
)
from roadsim.road.transition import build_transition

from .conftest import approx

WEST = Vec2(-70.0, 0.0)
NODE = Vec2(0.0, 0.0)
EAST = Vec2(70.0, 0.0)


def transition(
    west=AVENUE_FOUR_LANE, east=RESIDENTIAL_TWO_WAY, backwards: bool = False
):
    net = RoadNetwork()
    net.connect(WEST, NODE, west)
    # Drawn east-to-west on request: the second arm's A -> B then opposes the
    # first's, which flips what its own `+left` offsets mean.
    if backwards:
        net.connect(EAST, NODE, east)
    else:
        net.connect(NODE, EAST, east)
    net.rebuild_all()
    node = net.node_at(NODE).id
    junction = net.junctions[node]
    ends = net.segments_at(node)
    return build_transition(junction, {(s.id, at_a): s for s, at_a in ends})


def test_a_lane_count_change_gets_markings_across_the_patch():
    """The bug: two independent marking sets stopping at the mouths with an
    unmarked patch between them."""
    result = transition()
    assert result is not None
    assert result.markings


def test_the_same_profile_either_side_is_not_a_transition():
    """`build_junction` calls that a through joint and builds nothing at all,
    so there is no junction to carry markings across."""
    net = RoadNetwork()
    net.connect(WEST, NODE, RESIDENTIAL_TWO_WAY)
    net.connect(NODE, EAST, RESIDENTIAL_TWO_WAY)
    net.rebuild_all()
    assert net.node_at(NODE).id not in net.junctions


def test_a_crossing_is_not_a_transition():
    """Three arms is an intersection. Its paint is crosswalks and turn arrows,
    not lines carried through it."""
    net = RoadNetwork()
    net.connect(WEST, NODE, AVENUE_FOUR_LANE)
    net.connect(NODE, EAST, RESIDENTIAL_TWO_WAY)
    net.connect(NODE, Vec2(0.0, 70.0), RESIDENTIAL_TWO_WAY)
    net.rebuild_all()
    node = net.node_at(NODE).id
    ends = net.segments_at(node)
    junction = net.junctions[node]
    assert junction.is_crossing
    assert build_transition(junction, {(s.id, a): s for s, a in ends}) is None


def test_a_median_runs_back_to_the_single_centre_line_it_replaces():
    """The correspondence that matters: a road split by a median meets one
    split by a painted line, so both median edges have to reach that line.
    Drop it and the median simply stops in mid-air.
    """
    result = transition()
    medians = [m for m in result.markings if m.kind is MarkingKind.MEDIAN_EDGE]
    assert len(medians) == 2
    # Both converge on the same point - the two-lane road's centre line.
    a, b = medians
    shared = [p for p in (a.start, a.end) if p in (b.start, b.end)]
    assert len(shared) == 1


def test_a_gained_lanes_divider_tapers_instead_of_stopping_dead():
    result = transition()
    tapers = [m for m in result.markings if m.is_taper]
    assert tapers, "the surplus lane's divider had nowhere to go"
    for marking in tapers:
        assert marking.kind is MarkingKind.LANE_DIVIDER


def test_every_marking_actually_spans_the_patch():
    for marking in transition().markings:
        assert marking.start.distance_to(marking.end) > 0.0


def test_drawing_the_second_arm_backwards_gives_the_same_paint():
    """Each mouth's frame keeps its own segment's A -> B tangent, so two arms
    drawn in opposite directions have opposing normals. Miss that flip and the
    lines cross over each other instead of running straight across."""
    forward = transition()
    backward = transition(backwards=True)
    assert len(forward.markings) == len(backward.markings)
    ends = {
        (m.kind, round(min(m.start.y, m.end.y), 6), round(max(m.start.y, m.end.y), 6))
        for m in forward.markings
    }
    assert ends == {
        (m.kind, round(min(m.start.y, m.end.y), 6), round(max(m.start.y, m.end.y), 6))
        for m in backward.markings
    }


def test_markings_never_cross_the_patch_diagonally_past_each_other():
    """A line's two ends stay on the same side of the road. Crossing over is
    what a sign error in the frame flip looks like."""
    for marking in transition().markings:
        if marking.kind is MarkingKind.MEDIAN_EDGE:
            continue  # both edges legitimately converge on the centre line
        assert marking.start.y * marking.end.y >= 0.0


# -- merge arrows -----------------------------------------------------------


def test_losing_a_lane_earns_a_merge_arrow():
    result = transition()
    assert result.arrows
    assert all(a.decal.startswith("arrow_merge") for a in result.arrows)


def test_only_the_direction_that_loses_a_lane_gets_one():
    """Gaining a lane needs no instruction - a driver carries straight on and
    the new lane appears beside them."""
    result = transition()
    assert len(result.arrows) == 1


def test_a_merge_arrow_points_the_way_that_traffic_travels():
    result = transition()
    arrow = result.arrows[0]
    # Eastbound traffic loses a lane, so the arrow faces east.
    assert approx(arrow.forward.x, 1.0, 1e-9)
    assert approx(arrow.forward.y, 0.0, 1e-9)


def test_a_merge_arrow_sits_in_the_lane_that_is_running_out():
    result = transition()
    arrow = result.arrows[0]
    wide = AVENUE_FOUR_LANE
    outer = max(
        (wide.lane_center(k) for k in wide.forward_lanes), key=abs
    )
    assert approx(arrow.position.y, outer, 1e-6)


def test_a_merge_arrow_is_set_back_from_the_mouth_it_warns_about():
    """It is an instruction to change lane, so it has to arrive with room to
    act on it rather than at the point the lane has already gone."""
    result = transition()
    assert result.arrows[0].position.x < -1.0


@pytest.mark.parametrize("narrow", [RESIDENTIAL_TWO_WAY, ONE_WAY_TWO_LANE])
def test_a_transition_survives_every_shipped_pairing(narrow):
    result = transition(east=narrow)
    assert result is None or all(
        m.start.distance_to(m.end) > 0.0 for m in result.markings
    )
