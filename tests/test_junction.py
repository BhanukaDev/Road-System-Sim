"""Derived junction geometry: who pulls back how far, and where the mouths land.

The one that earns its place here is the asymmetric-profile test. `left` and
`right` flip at a `node_b` end, and that flip is the most likely bug in the
whole milestone - so it is asserted both structurally (on `SegmentEnd`) and
behaviourally (draw the same road backwards, get the same junction).
"""

from __future__ import annotations

import pytest

from roadsim import config
from roadsim.geometry import ArcSegment, Path, Vec2
from roadsim.road.junction import SegmentEnd, build_junction
from roadsim.road.lane import Direction, LaneSpec, LaneType
from roadsim.road.network import RoadNetwork
from roadsim.road.presets import RESIDENTIAL_TWO_WAY, TRAM_AVENUE
from roadsim.road.profile import RoadProfile

from .conftest import approx

ORIGIN = Vec2(0.0, 0.0)
NARROW = RESIDENTIAL_TWO_WAY  # 11 m wide, half-width 5.5
WIDE = TRAM_AVENUE  # 14 m wide, half-width 7.0

LOPSIDED = RoadProfile(
    "lopsided",
    (
        LaneSpec(2.0, Direction.NONE, LaneType.SIDEWALK),
        LaneSpec(3.5, Direction.BACKWARD, LaneType.CAR),
        LaneSpec(3.5, Direction.FORWARD, LaneType.CAR),
        LaneSpec(3.5, Direction.FORWARD, LaneType.CAR),
        LaneSpec(6.0, Direction.NONE, LaneType.SHOULDER),
    ),
    datum=-3.0,
)
"""Deliberately off-centre: 6.25 m left of the centreline, 12.25 m right of it.
The datum is what does that - an unbalanced lane list alone stays centred."""


def crossing(east_west=NARROW, north_south=NARROW, reversed_ew: bool = False):
    """Four arms meeting at the origin, one profile per axis."""
    net = RoadNetwork()
    west, east = Vec2(-70.0, 0.0), Vec2(70.0, 0.0)
    if reversed_ew:
        net.connect(ORIGIN, west, east_west)
        net.connect(east, ORIGIN, east_west)
    else:
        net.connect(west, ORIGIN, east_west)
        net.connect(ORIGIN, east, east_west)
    net.connect(Vec2(0.0, -70.0), ORIGIN, north_south)
    net.connect(ORIGIN, Vec2(0.0, 70.0), north_south)
    net.rebuild_all()
    return net


def arm_trim(net: RoadNetwork, direction: Vec2) -> float:
    """Trim of the arm leaving the origin in roughly `direction`."""
    hub = net.node_at(ORIGIN).id
    for segment, at_a in net.segments_at(hub):
        if segment.outgoing_dir(at_a).dot(direction) > 0.9:
            return segment.trim_a if at_a else segment.trim_b
    raise AssertionError(f"no arm leaving {direction}")


# -- the left/right flip at a node_b end ----------------------------------


def test_segment_end_flips_left_and_right_at_the_b_end():
    net = RoadNetwork()
    seg = net.connect(Vec2(-70.0, 0.0), ORIGIN, LOPSIDED)
    at_a, at_b = SegmentEnd.of(seg, True), SegmentEnd.of(seg, False)

    assert approx(at_a.extent_left, LOPSIDED.extent_left)
    assert approx(at_a.extent_right, LOPSIDED.extent_right)
    assert approx(at_b.extent_left, LOPSIDED.extent_right)
    assert approx(at_b.extent_right, LOPSIDED.extent_left)


def test_an_asymmetric_road_trims_its_neighbours_by_which_side_they_are_on():
    """The wide side of the road forces the bigger pull-back on the arm facing it.

    Every corner here is a right angle, so its fillet gives back exactly its own
    radius of tangent (`tan(45 degrees) == 1`): each arm clears the kerb it
    crosses and then that much again.
    """
    net = crossing(east_west=LOPSIDED)
    north = arm_trim(net, Vec2(0.0, 1.0))
    south = arm_trim(net, Vec2(0.0, -1.0))
    corner = config.JUNCTION_CORNER_RADIUS
    assert south > north
    assert approx(north, LOPSIDED.extent_left + corner, 1e-6)
    assert approx(south, LOPSIDED.extent_right + corner, 1e-6)


def test_drawing_the_asymmetric_road_backwards_mirrors_the_junction():
    """Reverse the road's A -> B direction and its wide side changes sides, so
    the junction must mirror north for south - exactly, and with the arms along
    the road itself untouched.

    This is the behavioural half of the `node_b` left/right flip. Get the flip
    wrong and the two crossings come out identical instead of mirrored, which
    nothing else in the milestone catches.
    """
    forward = crossing(east_west=LOPSIDED)
    backward = crossing(east_west=LOPSIDED, reversed_ew=True)
    north, south = Vec2(0.0, 1.0), Vec2(0.0, -1.0)
    assert approx(arm_trim(backward, north), arm_trim(forward, south), 1e-6)
    assert approx(arm_trim(backward, south), arm_trim(forward, north), 1e-6)
    for along in (Vec2(1.0, 0.0), Vec2(-1.0, 0.0)):
        assert approx(arm_trim(backward, along), arm_trim(forward, along), 1e-6)


# -- trimming ------------------------------------------------------------


def test_a_four_way_crossing_trims_every_arm():
    net = crossing()
    for segment in net.segments.values():
        assert segment.trim_a + segment.trim_b > 0.0
    assert len(net.junctions) == 1


def test_a_wider_road_forces_a_larger_trim_on_the_road_it_crosses():
    net = crossing(east_west=WIDE, north_south=NARROW)
    north_south_trim = arm_trim(net, Vec2(0.0, 1.0))
    # The narrow road gives up more than it would at a junction of its own kind,
    # and exactly enough to clear the wide one.
    corner = config.JUNCTION_CORNER_RADIUS
    assert north_south_trim > NARROW.half_width + corner
    assert approx(north_south_trim, WIDE.half_width + corner, 1e-6)
    # The wide road only has the narrow one's kerb to clear, so it stops
    # sooner - its own half-width is no longer what decides where it stops.
    assert approx(arm_trim(net, Vec2(1.0, 0.0)), NARROW.half_width + corner, 1e-6)


def test_no_arm_is_ever_trimmed_less_than_its_own_half_width():
    """Otherwise the junction would be narrower than the roads feeding it."""
    net = crossing(east_west=WIDE, north_south=NARROW)
    for segment in net.segments.values():
        for at_a in (True, False):
            node = segment.node_a if at_a else segment.node_b
            if net.nodes[node].degree > 1:
                trim = segment.trim_a if at_a else segment.trim_b
                assert trim >= segment.profile.half_width - 1e-9


def test_a_dead_end_is_not_trimmed():
    net = RoadNetwork()
    seg = net.connect(Vec2(-70.0, 0.0), ORIGIN, NARROW)
    net.rebuild_all()
    assert seg.trim_a == 0.0 and seg.trim_b == 0.0
    assert not net.junctions


# -- when a junction exists at all ---------------------------------------


def test_a_straight_run_through_one_profile_is_not_a_junction():
    net = RoadNetwork()
    net.connect(Vec2(-70.0, 0.0), ORIGIN, NARROW)
    net.connect(ORIGIN, Vec2(70.0, 0.0), NARROW)
    net.rebuild_all()
    assert not net.junctions
    assert all(s.trim_a == s.trim_b == 0.0 for s in net.segments.values())


def test_a_kink_in_one_profile_still_gets_a_junction():
    """Same cross-section either side, but there is still a corner to cut."""
    net = RoadNetwork()
    net.connect(Vec2(-70.0, 0.0), ORIGIN, NARROW)
    net.connect(ORIGIN, Vec2(40.0, 60.0), NARROW)
    net.rebuild_all()
    assert len(net.junctions) == 1


def test_two_different_profiles_meeting_end_to_end_get_a_transition_patch():
    net = RoadNetwork()
    net.connect(Vec2(-70.0, 0.0), ORIGIN, NARROW)
    net.connect(ORIGIN, Vec2(70.0, 0.0), WIDE)
    net.rebuild_all()
    junction = net.junctions[net.node_at(ORIGIN).id]
    assert len(junction.ends) == 2
    assert not junction.is_crossing


# -- the polygon ----------------------------------------------------------


def test_the_polygon_has_two_corners_per_arm():
    net = crossing()
    junction = net.junctions[net.node_at(ORIGIN).id]
    assert len(junction.polygon) == 2 * len(junction.ends)


def test_polygon_corners_sit_on_the_trimmed_mouths():
    """The junction surface is flush with the ribbons that stop against it."""
    net = crossing(east_west=WIDE)
    hub = net.node_at(ORIGIN).id
    junction = net.junctions[hub]
    corners = set()
    for segment, at_a in net.segments_at(hub):
        frame = segment.end_frame(at_a)
        for edge in (segment.profile.edges[0], segment.profile.edges[-1]):
            corners.add(tuple(frame.position + frame.normal * edge))
    for corner in junction.polygon:
        assert min(Vec2(*c).distance_to(corner) for c in corners) <= 1e-9


def test_ends_are_sorted_counter_clockwise():
    net = crossing()
    junction = net.junctions[net.node_at(ORIGIN).id]
    angles = [end.angle % (2.0 * 3.141592653589793) for end in junction.ends]
    assert angles == sorted(angles)


def test_a_single_end_builds_no_junction():
    net = RoadNetwork()
    seg = net.connect(Vec2(-70.0, 0.0), ORIGIN, NARROW)
    assert build_junction(seg.node_b, ORIGIN, [(seg, False)]) is None


@pytest.mark.parametrize("profile", [NARROW, WIDE, LOPSIDED])
def test_trims_leave_the_carriageway_intact_on_a_normal_crossing(profile):
    net = crossing(east_west=profile, north_south=profile)
    assert all(not s.is_too_short for s in net.segments.values())


# -- exact trims, replacing the M2 tangent-ray approximation ---------------


def test_exact_trim_follows_a_curved_kerb_instead_of_a_straight_tangent(monkeypatch):
    """The M2 debt this closes: a curve starting right at the node used to
    trim against the straight tangent line it left on, not its own shape.

    A shallow corner is the case that shows it: the straight-tangent version
    has nowhere real to cross, so it runs into `JUNCTION_MAX_TRIM_FACTOR`'s
    cap instead of an answer. Bending the same arm's kerb away finds a real,
    smaller crossing well inside that cap - a different number, not just a
    smaller share of the same approximation.

    `fit_polyline` never puts an arc at a segment's very end - only *between*
    two straights - so the only way to get one there for a test is to replace
    `path` directly after construction.

    Corner rounding is switched off for the same reason the angle is shallow: a
    wedge this sharp needs an enormous tangent for any radius at all, so the
    fillet would soak up whatever the cap left either way and hide the crossing
    this is about. Where the *corner* lands is `test_a_corner_fillet_...`'s job.
    """
    monkeypatch.setattr(config, "JUNCTION_CORNER_RADIUS", 0.0)
    tilted = Vec2(-45.0, 12.0)  # shallow relative to the west arm below

    def trim_with(path_override: Path | None) -> float:
        net = RoadNetwork()
        net.connect(Vec2(-50.0, 0.0), ORIGIN, NARROW)
        arm = net.connect(ORIGIN, tilted, NARROW)
        if path_override is not None:
            arm.path = path_override
        net.rebuild_all()
        return arm.trim_a

    straight_trim = trim_with(None)
    assert approx(
        straight_trim, config.JUNCTION_MAX_TRIM_FACTOR * NARROW.half_width, 1e-6
    )

    entry_dir = tilted.normalized()
    bent = ArcSegment.from_tangent_points(ORIGIN, entry_dir, Vec2(-60.0, 40.0), 20.0)
    curved_trim = trim_with(Path.of(bent))

    assert not approx(curved_trim, straight_trim, 1e-6)
    assert curved_trim < straight_trim


# -- rounded corners --------------------------------------------------------


def test_every_corner_of_a_four_way_crossing_is_rounded():
    net = crossing()
    junction = net.junctions[net.node_at(ORIGIN).id]
    assert len(junction.corners) == len(junction.ends)
    assert all(corner is not None for corner in junction.corners)


def test_a_corner_fillet_is_tangent_to_both_kerbs():
    net = crossing()
    junction = net.junctions[net.node_at(ORIGIN).id]
    n = len(junction.ends)
    for i, fillet in enumerate(junction.corners):
        a, b = junction.ends[i], junction.ends[(i + 1) % n]
        into, out_of = -a.outgoing_dir, b.outgoing_dir
        assert approx(fillet.arc.start.tangent.cross(into), 0.0, 1e-6)
        assert approx(fillet.arc.end.tangent.cross(out_of), 0.0, 1e-6)


def test_a_short_arms_corners_are_clamped_below_the_default_radius():
    """A corner can only use the kerb its arms still have past the crossing, so
    stubby arms clamp it below the default - exactly as `fit_polyline`'s fillets
    clamp on a short leg."""
    stub = 9.0
    net = RoadNetwork()
    for direction in (Vec2(1.0, 0.0), Vec2(-1.0, 0.0), Vec2(0.0, 1.0), Vec2(0.0, -1.0)):
        net.connect(ORIGIN, direction * stub, NARROW)
    net.rebuild_all()
    junction = net.junctions[net.node_at(ORIGIN).id]
    for fillet in junction.corners:
        assert fillet.radius < config.JUNCTION_CORNER_RADIUS
        assert approx(fillet.radius, stub - NARROW.half_width, 1e-6)


def test_a_roomy_crossings_corners_take_the_default_radius():
    net = crossing(east_west=WIDE, north_south=WIDE)
    junction = net.junctions[net.node_at(ORIGIN).id]
    for fillet in junction.corners:
        assert approx(fillet.radius, config.JUNCTION_CORNER_RADIUS, 1e-6)


# -- the corner handle -------------------------------------------------------


def _east_arm(net: RoadNetwork, hub: int):
    return next(
        seg
        for seg, at_a in net.segments_at(hub)
        if at_a and seg.outgoing_dir(at_a).dot(Vec2(1.0, 0.0)) > 0.9
    )


def test_a_pulled_arm_is_trimmed_by_its_pull_past_the_kerb_crossing():
    """The pull is the tangent length, so it is measured from the corner - the
    mouth lands that far back from where the kerbs cross, which is where the
    corner arc actually leaves the kerb."""
    net = crossing()
    hub = net.node_at(ORIGIN).id
    east_arm = _east_arm(net, hub)
    east_arm.pull_a = 9.0
    net.rebuild_all()
    assert approx(east_arm.trim_a, NARROW.half_width + 9.0, 1e-6)


def test_pulling_every_arm_out_grows_the_corners_to_match():
    """Decision 7: the handle sets the trim and the radius together - pull
    every arm back the same amount and every corner (all 90 degrees, here)
    should grow to exactly that pull rather than staying clamped at whatever
    it derived before."""
    net = crossing()
    hub = net.node_at(ORIGIN).id
    before = next(f.radius for f in net.junctions[hub].corners if f is not None)

    pulled = before + 3.0
    for segment, at_a in net.segments_at(hub):
        if at_a:
            segment.pull_a = pulled
        else:
            segment.pull_b = pulled
    net.rebuild_all()

    after = net.junctions[hub].corners
    assert all(f is not None and approx(f.radius, pulled, 1e-6) for f in after)
