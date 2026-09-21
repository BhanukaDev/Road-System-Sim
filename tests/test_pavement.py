"""Pavement bands round a rounded junction corner.

The one invariant that matters is concentricity: `curb` and `inner` share a
centre and are exactly one sidewalk width apart at every sampled angle, not
just at their tangent points. Which side `inner` sits on matters just as much -
a corner arc curves around a centre out in the empty corner, so the edge facing
the carriageway is the *larger* radius, and getting that backwards throws the
footway off into the block.
"""

from __future__ import annotations

from roadsim.geometry import Vec2
from roadsim.road.network import RoadNetwork
from roadsim.road.pavement import build_pavement_bands
from roadsim.road.presets import (
    ASYMMETRIC_BOULEVARD,
    RAIL_DOUBLE,
    RESIDENTIAL_TWO_WAY,
)

from .conftest import approx, assert_vec

ORIGIN = Vec2(0.0, 0.0)
NARROW = RESIDENTIAL_TWO_WAY


def crossing(east_west=NARROW, north_south=NARROW) -> RoadNetwork:
    net = RoadNetwork()
    net.connect(Vec2(-70.0, 0.0), ORIGIN, east_west)
    net.connect(ORIGIN, Vec2(70.0, 0.0), east_west)
    net.connect(Vec2(0.0, -70.0), ORIGIN, north_south)
    net.connect(ORIGIN, Vec2(0.0, 70.0), north_south)
    net.rebuild_all()
    return net


def test_a_pavement_band_is_concentric_with_its_corner():
    net = crossing()
    hub = net.node_at(ORIGIN).id
    junction = net.junctions[hub]
    seg_by_key = {(s.id, at_a): s for s, at_a in net.segments_at(hub)}
    bands = build_pavement_bands(junction, seg_by_key)
    assert len(bands) == len(junction.ends)

    width = NARROW.lanes[0].width
    for band in bands:
        assert band.curb is not None
        assert band.inner is not None
        assert_vec(band.curb.center, band.inner.center)
        assert approx(band.inner.radius - band.curb.radius, width, 1e-6)
        assert band.inner.center.distance_to(ORIGIN) > band.curb.radius
        next_corner = 2 * ((band.corner_index + 1) % len(junction.ends))
        assert_vec(band.outer_start, junction.polygon[2 * band.corner_index + 1])
        assert_vec(band.outer_end, junction.polygon[next_corner])
        for t in (0.0, 0.3, 0.7, 1.0):
            inner_point = band.curb.sample(t * band.curb.length).position
            outer_point = band.inner.sample(t * band.inner.length).position
            assert approx(inner_point.distance_to(outer_point), width, 1e-6)


def test_no_sidewalk_means_no_pavement_band():
    net = crossing(east_west=RAIL_DOUBLE, north_south=RAIL_DOUBLE)
    hub = net.node_at(ORIGIN).id
    junction = net.junctions[hub]
    seg_by_key = {(s.id, at_a): s for s, at_a in net.segments_at(hub)}
    assert build_pavement_bands(junction, seg_by_key) == ()


def test_straight_profile_change_connects_both_sidewalks():
    net = RoadNetwork()
    net.connect(Vec2(-70.0, 0.0), ORIGIN, RESIDENTIAL_TWO_WAY)
    changed = net.connect(ORIGIN, Vec2(70.0, 0.0), RESIDENTIAL_TWO_WAY)
    net.rebuild_all()
    assert not net.junctions

    net.set_profile(changed.id, ASYMMETRIC_BOULEVARD)
    net.rebuild_dirty()

    hub = net.node_at(ORIGIN).id
    junction = net.junctions[hub]
    seg_by_key = {(segment.id, at_a): segment for segment, at_a in net.segments_at(hub)}
    bands = build_pavement_bands(junction, seg_by_key)

    assert len(bands) == 2
    assert all(band.curb is None and band.inner is None for band in bands)
    for band in bands:
        next_corner = 2 * ((band.corner_index + 1) % len(junction.ends))
        assert_vec(band.outer_start, junction.polygon[2 * band.corner_index + 1])
        assert_vec(band.outer_end, junction.polygon[next_corner])


def test_profile_change_keeps_pavements_inside_their_kerbs():
    net = crossing()
    hub = net.node_at(ORIGIN).id
    east_arm = next(
        segment
        for segment, at_a in net.segments_at(hub)
        if at_a and segment.outgoing_dir(at_a).dot(Vec2(1.0, 0.0)) > 0.9
    )
    net.set_profile(east_arm.id, ASYMMETRIC_BOULEVARD)
    net.rebuild_dirty()

    junction = net.junctions[hub]
    seg_by_key = {(segment.id, at_a): segment for segment, at_a in net.segments_at(hub)}
    bands = build_pavement_bands(junction, seg_by_key)

    assert len(bands) == len(junction.ends)
    for band in bands:
        assert approx(
            band.inner.radius - band.curb.radius,
            RESIDENTIAL_TWO_WAY.lanes[0].width,
            1e-6,
        )
