"""Handles along a placed road's own shape.

Every handle is derived from `segment.path.pieces`, so the invariants worth
proving are geometric: a handle sits exactly on the path at its own `s`,
handles are ordered and non-overlapping, and `ARC_MID`'s claimed owner really
is the control point that produced the arc it sits on. Materialising a
`STRAIGHT_MID` should be invisible - the whole point of picking a collinear
insertion point - so that gets its own exactness proof.
"""

from __future__ import annotations

import pytest

from roadsim.geometry import ArcSegment, LineSegment, Vec2, fit_polyline
from roadsim.road.network import RoadNetwork
from roadsim.road.presets import RESIDENTIAL_TWO_WAY
from roadsim.road.shape_handle import (
    ShapeHandleKind,
    insert_index,
    materialise,
    radius_for_arc_end,
    shape_handles,
)

from .conftest import assert_vec

ORIGIN = Vec2(0.0, 0.0)
EAST = Vec2(60.0, 0.0)


def _bent_segment(net: RoadNetwork):
    """One corner, filleted - a control point with a real ARC_MID / ARC_END
    triple and a straight on either side."""
    return net.connect(
        Vec2(-60.0, 0.0),
        Vec2(0.0, 60.0),
        RESIDENTIAL_TWO_WAY,
        via=[Vec2(0.0, 0.0)],
    )


def _zigzag_segment(net: RoadNetwork):
    """Three corners, so more than one control point is in play at once."""
    return net.connect(
        Vec2(-90.0, -30.0),
        Vec2(95.0, -25.0),
        RESIDENTIAL_TWO_WAY,
        via=[Vec2(-10.0, 20.0), Vec2(30.0, 25.0), Vec2(45.0, -20.0)],
    )


# -- every handle sits exactly on the path ----------------------------------


def test_every_derived_handle_sits_on_the_path_at_its_own_s():
    """True for every kind *except* `CONTROL`: a filleted corner cuts inside
    its own control point (`road/network.py:_corner_points`'s own docstring),
    so a `CONTROL` handle is deliberately drawn at the true corner, off the
    path its own `s` was found by projecting onto."""
    net = RoadNetwork()
    segment = _zigzag_segment(net)

    for handle in shape_handles(segment):
        if handle.kind is ShapeHandleKind.CONTROL:
            continue
        assert_vec(handle.position, segment.path.sample(handle.s).position)


def test_handle_s_values_are_sorted_and_interior():
    """Non-decreasing, not strictly - a `CONTROL` handle's `s` is a projection
    onto the path and can legitimately coincide with its own arc's `ARC_MID` /
    `ARC_END`, since a symmetric fillet projects its corner back near its own
    belly. What must never happen is two handles landing at the node ends."""
    net = RoadNetwork()
    segment = _zigzag_segment(net)
    handles = shape_handles(segment)

    values = [h.s for h in handles]
    assert values == sorted(values)
    assert all(0.0 < s < segment.path.length for s in values)


# -- a straight road has one straight-mid and no arcs ------------------------


def test_a_straight_road_yields_one_straight_mid_and_no_arcs():
    net = RoadNetwork()
    segment = net.connect(ORIGIN, EAST, RESIDENTIAL_TWO_WAY)
    handles = shape_handles(segment)

    assert [h.kind for h in handles] == [ShapeHandleKind.STRAIGHT_MID]
    assert_vec(handles[0].position, Vec2(30.0, 0.0))


# -- every corner is a CONTROL handle, and a real fillet owns an ARC_MID -----


def test_every_interior_control_point_gets_a_control_handle():
    net = RoadNetwork()
    segment = _zigzag_segment(net)
    handles = shape_handles(segment)

    controls = [h for h in handles if h.kind is ShapeHandleKind.CONTROL]
    assert len(controls) == len(segment.control_points) - 2
    for handle, point in zip(controls, segment.control_points[1:-1]):
        assert_vec(handle.position, point)


def test_arc_mid_resolves_to_a_real_control_point():
    net = RoadNetwork()
    segment = _bent_segment(net)
    handles = shape_handles(segment)

    arc_mids = [h for h in handles if h.kind is ShapeHandleKind.ARC_MID]
    assert len(arc_mids) == 1
    assert arc_mids[0].control_index is not None
    owned_point = segment.control_points[arc_mids[0].control_index]
    assert_vec(owned_point, Vec2(0.0, 0.0))  # the corner it belongs to

    arc_ends = [h for h in handles if h.kind is ShapeHandleKind.ARC_END]
    assert len(arc_ends) == 2


def test_a_kinked_corner_gets_no_arc_handles():
    """`fit_polyline` leaves a corner too sharp for its radius as a hard kink -
    `corner_fillet` returns `None` - so there is no arc there to hand out
    `ARC_MID` / `ARC_END` handles for, only the `CONTROL` point itself."""
    net = RoadNetwork()
    # A dead-straight reversal: 180 degrees, no arc can join it (fillet.py).
    segment = net.add_segment(
        net.add_node(Vec2(0.0, 0.0)).id,
        net.add_node(Vec2(-60.0, 0.0)).id,
        [Vec2(0.0, 0.0), Vec2(30.0, 0.0), Vec2(0.0, 0.0), Vec2(-60.0, 0.0)],
        RESIDENTIAL_TWO_WAY,
    )
    assert not any(isinstance(p, ArcSegment) for p in segment.path.pieces)

    handles = shape_handles(segment)
    assert {h.kind for h in handles} <= {
        ShapeHandleKind.CONTROL,
        ShapeHandleKind.STRAIGHT_MID,
    }
    assert not any(h.kind is ShapeHandleKind.ARC_MID for h in handles)


# -- insert_index --------------------------------------------------------


def test_insert_index_places_a_point_between_its_neighbours():
    net = RoadNetwork()
    segment = _zigzag_segment(net)
    path = segment.path

    for handle in shape_handles(segment):
        if handle.kind is not ShapeHandleKind.STRAIGHT_MID:
            continue
        index = insert_index(segment, handle.s)
        before_s = path.project(segment.control_points[index - 1])
        after_s = path.project(segment.control_points[index])
        assert before_s <= handle.s <= after_s


# -- materialising a STRAIGHT_MID is provably invisible ----------------------


def test_materialising_a_straight_mid_does_not_move_the_path():
    net = RoadNetwork()
    segment = net.connect(ORIGIN, EAST, RESIDENTIAL_TWO_WAY)
    before_length = segment.path.length
    samples_before = [
        segment.path.sample(s).position for s in range(0, 61, 5)
    ]

    handle = next(
        h for h in shape_handles(segment) if h.kind is ShapeHandleKind.STRAIGHT_MID
    )
    points, index = materialise(segment, handle)
    assert points[index] == handle.position
    assert len(points) == len(segment.control_points) + 1

    refit = fit_polyline(points, segment.corner_radius)
    assert refit.length == pytest.approx(before_length, abs=1e-9)
    for s, before in zip(range(0, 61, 5), samples_before):
        assert_vec(refit.sample(float(s)).position, before)


def test_materialise_leaves_control_and_arc_mid_handles_alone():
    """`CONTROL` and `ARC_MID` already own a point - materialising must return
    the *same* list, not insert a duplicate."""
    net = RoadNetwork()
    segment = _bent_segment(net)

    for handle in shape_handles(segment):
        if handle.control_index is None:
            continue
        points, index = materialise(segment, handle)
        assert points == segment.control_points
        assert index == handle.control_index


def test_materialise_refuses_an_arc_end():
    net = RoadNetwork()
    segment = _bent_segment(net)
    arc_end = next(
        h for h in shape_handles(segment) if h.kind is ShapeHandleKind.ARC_END
    )
    with pytest.raises(ValueError):
        materialise(segment, arc_end)


# -- radius_for_arc_end -------------------------------------------------


def test_radius_for_arc_end_round_trips_at_its_own_position():
    """Dropping the handle back where it already is must reproduce the radius
    that put it there - `corner_fillet`'s own identity, inverted."""
    net = RoadNetwork()
    segment = _bent_segment(net)
    arc_end = next(
        h for h in shape_handles(segment) if h.kind is ShapeHandleKind.ARC_END
    )

    radius = radius_for_arc_end(segment, arc_end, arc_end.position)
    assert radius == pytest.approx(segment.corner_radius, abs=1e-6)


def test_radius_for_arc_end_grows_with_distance_from_the_corner():
    net = RoadNetwork()
    segment = _bent_segment(net)
    arc_end = next(
        h for h in shape_handles(segment) if h.kind is ShapeHandleKind.ARC_END
    )
    corner = segment.control_points[1]
    direction = (arc_end.position - corner).normalized()

    near = radius_for_arc_end(segment, arc_end, corner + direction * 2.0)
    far = radius_for_arc_end(segment, arc_end, corner + direction * 20.0)
    assert far > near


def test_radius_for_arc_end_never_goes_below_min_radius():
    from roadsim.geometry.fillet import MIN_RADIUS

    net = RoadNetwork()
    segment = _bent_segment(net)
    arc_end = next(
        h for h in shape_handles(segment) if h.kind is ShapeHandleKind.ARC_END
    )
    corner = segment.control_points[1]

    radius = radius_for_arc_end(segment, arc_end, corner)  # dragged onto the corner
    assert radius >= MIN_RADIUS
