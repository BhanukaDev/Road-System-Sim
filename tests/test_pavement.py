"""Pavement bands round a junction corner.

The one invariant that matters is constant width: `inner` is exactly one
sidewalk width from `curb` at every point along it, not just at the ends. Which
side `inner` sits on matters just as much - the mouths are walked
counter-clockwise, so the carriageway is on the kerb's left the whole way round,
and getting that backwards throws the footway off into the block.

Stated as a distance rather than as "two arcs sharing a centre" on purpose. The
kerb across a corner is a biarc, so there is no single centre to share, and the
width is the thing a pedestrian would actually notice.
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

from .conftest import assert_vec


def assert_band_width(band, width: float) -> None:
    """`inner` is `width` to the kerb's left, everywhere along it.

    Matched by projecting back onto the kerb rather than by arc-length fraction:
    offsetting an arc changes its length, so the same fraction along a biarc and
    its offset are not the same point.
    """
    assert band.curb is not None
    assert band.inner is not None
    for s in band.inner.flatten(1e-3):
        point = band.inner.sample(s).position
        frame = band.curb.sample(band.curb.project(point))
        assert_vec(point, frame.position + frame.normal * width)


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


def test_a_pavement_band_keeps_its_width_the_whole_way_round():
    net = crossing()
    hub = net.node_at(ORIGIN).id
    junction = net.junctions[hub]
    seg_by_key = {(s.id, at_a): s for s, at_a in net.segments_at(hub)}
    bands = build_pavement_bands(junction, seg_by_key)
    assert len(bands) == len(junction.ends)

    width = NARROW.lanes[0].width
    for band in bands:
        assert_band_width(band, width)
        next_corner = 2 * ((band.corner_index + 1) % len(junction.ends))
        assert_vec(band.outer_start, junction.polygon[2 * band.corner_index + 1])
        assert_vec(band.outer_end, junction.polygon[next_corner])
        # The kerb starts and ends on the mouths themselves - not short of them,
        # which is what let a corner solved at the kerbs' apex float free of the
        # road it was meant to join.
        assert_vec(band.curb.start.position, band.outer_start)
        assert_vec(band.curb.end.position, band.outer_end)


def test_no_sidewalk_means_no_pavement_band():
    net = crossing(east_west=RAIL_DOUBLE, north_south=RAIL_DOUBLE)
    hub = net.node_at(ORIGIN).id
    junction = net.junctions[hub]
    seg_by_key = {(s.id, at_a): s for s, at_a in net.segments_at(hub)}
    assert build_pavement_bands(junction, seg_by_key) == ()


def test_straight_profile_change_bends_the_kerb_across_instead_of_cutting_it():
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
    for band in bands:
        next_corner = 2 * ((band.corner_index + 1) % len(junction.ends))
        assert_vec(band.outer_start, junction.polygon[2 * band.corner_index + 1])
        assert_vec(band.outer_end, junction.polygon[next_corner])
        # Two profiles of different width meet head on: the kerbs are parallel
        # but offset, so the join is an S-bend between them, not the diagonal
        # chord the old straight-quad fallback drew.
        assert band.curb is not None
        assert_vec(band.curb.start.position, band.outer_start)
        assert_vec(band.curb.end.position, band.outer_end)
        assert_vec(band.curb.start.tangent, band.curb.end.tangent)
        assert_band_width(band, RESIDENTIAL_TWO_WAY.lanes[0].width)


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
        assert_band_width(band, RESIDENTIAL_TWO_WAY.lanes[0].width)


def test_a_shallow_merge_gets_a_footway_round_its_nose_not_a_quad_across_it():
    """The symptom that made shallow Y junctions unbuildable.

    With no kerb at the corner, `build_pavement_bands` falls back to a straight
    quad between the two mouths - and at a shallow angle those mouths are tens
    of metres apart on either side of both carriageways, so the "footway" was a
    long thin slab laid over the road. The blend gives the band a real nose to
    follow, one sidewalk width wide by construction.
    """
    import math

    net = RoadNetwork()
    length = 200.0
    net.connect(Vec2(-length, 0.0), ORIGIN, NARROW)
    net.connect(ORIGIN, Vec2(length, 0.0), NARROW)
    radians = math.radians(10.0)
    net.connect(
        ORIGIN,
        Vec2(length * math.cos(radians), length * math.sin(radians)),
        NARROW,
    )
    net.rebuild_all()

    junction = net.junctions[net.node_at(ORIGIN).id]
    assert not junction.is_degenerate
    ends = net.segments_at(junction.node_id)
    bands = build_pavement_bands(junction, {(s.id, at_a): s for s, at_a in ends})

    nose = [b for b in bands if b.curb is not None]
    assert nose, "the gore corner fell back to a straight quad"
    for band in nose:
        assert_band_width(band, NARROW.lanes[0].width)
