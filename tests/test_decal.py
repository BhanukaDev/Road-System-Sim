"""Painted decals: the normalised frame, and placing one on a road.

The invariants here are about the *frame* - centred, unit length, +y along
travel - because everything downstream scales and rotates against it. A decal
whose origin is off-centre puts every arrow off-centre in its lane, which is
the kind of wrong that looks like a rendering bug.
"""

from __future__ import annotations

import pytest

from roadsim.geometry import Vec2
from roadsim.road.decal import DECALS, Decal, get
from roadsim.road.turn_arrows import TURN_DECALS, TurnKind

from .conftest import approx, assert_vec

NAMES = sorted(DECALS)

ROUNDING = 2e-6
"""`decal_library.py` is generated with six decimal places, so this is the
tightest any assertion about its contents can honestly be - unlike the rest of
the suite, the limit here is the file format, not the arithmetic. Everything
below that is computed rather than stored is still asserted at `EXACT`."""


def bounds(rings) -> tuple[float, float, float, float]:
    xs = [p.x for ring in rings for p in ring]
    ys = [p.y for ring in rings for p in ring]
    return min(xs), max(xs), min(ys), max(ys)


@pytest.mark.parametrize("name", NAMES)
def test_every_decal_is_exactly_one_long_along_travel(name: str):
    _, _, lo, hi = bounds(DECALS[name].rings)
    assert approx(hi - lo, 1.0, ROUNDING)


@pytest.mark.parametrize("name", NAMES)
def test_every_decal_is_centred_on_its_own_origin(name: str):
    x0, x1, y0, y1 = bounds(DECALS[name].rings)
    assert approx((x0 + x1) / 2.0, 0.0, ROUNDING)
    assert approx((y0 + y1) / 2.0, 0.0, ROUNDING)


@pytest.mark.parametrize("name", NAMES)
def test_the_recorded_aspect_matches_the_rings(name: str):
    decal = DECALS[name]
    x0, x1, _, _ = bounds(decal.rings)
    assert approx(decal.aspect, x1 - x0, ROUNDING)


@pytest.mark.parametrize("name", NAMES)
def test_every_ring_is_a_ring(name: str):
    assert DECALS[name].rings
    for ring in DECALS[name].rings:
        assert len(ring) >= 3


def test_every_turn_option_has_a_decal():
    """The registry line is the whole of adding an option (rule 2), so a kind
    without one is a gap that should fail here rather than at the first frame
    it is drawn."""
    for kind in TurnKind:
        assert kind in TURN_DECALS
        assert get(kind.decal).name == TURN_DECALS[kind]


# -- placement --------------------------------------------------------------


def unit_square() -> Decal:
    ring = (Vec2(-0.5, -0.5), Vec2(0.5, -0.5), Vec2(0.5, 0.5), Vec2(-0.5, 0.5))
    return Decal("square", (ring,), 1.0)


def test_placing_a_decal_scales_it_and_puts_it_where_it_was_asked():
    placed = unit_square().placed(Vec2(10.0, 4.0), Vec2(0.0, 1.0), 2.0)
    xs = [p.x for p in placed[0]]
    ys = [p.y for p in placed[0]]
    assert approx(min(xs), 9.0) and approx(max(xs), 11.0)
    assert approx(min(ys), 3.0) and approx(max(ys), 5.0)


def test_a_decals_own_up_points_the_way_traffic_travels():
    """+y in the normalised frame is the direction of travel, whichever way the
    road is pointing."""
    nose = Decal("nose", ((Vec2(0.0, 0.5), Vec2(-0.1, -0.5), Vec2(0.1, -0.5)),), 0.2)
    east = nose.placed(Vec2(0.0, 0.0), Vec2(1.0, 0.0), 2.0)
    assert_vec(east[0][0], Vec2(1.0, 0.0))
    west = nose.placed(Vec2(0.0, 0.0), Vec2(-1.0, 0.0), 2.0)
    assert_vec(west[0][0], Vec2(-1.0, 0.0))


def test_a_decals_own_right_is_the_drivers_right():
    """`normal = tangent.rot90()` points left (D3), so +x has to be its
    negation - get this backwards and every turn arrow mirrors."""
    flag = Decal("flag", ((Vec2(0.5, 0.0), Vec2(0.0, 0.5), Vec2(0.0, -0.5)),), 1.0)
    # Travelling north, the driver's right is east.
    placed = flag.placed(Vec2(0.0, 0.0), Vec2(0.0, 1.0), 1.0)
    assert placed[0][0].x > 0.0


def test_a_narrow_lane_gets_a_shorter_decal_not_a_squashed_one():
    wide = Decal("wide", ((Vec2(-0.25, -0.5), Vec2(0.25, -0.5), Vec2(0.0, 0.5)),), 0.5)
    assert approx(wide.fitted_length(4.0, 10.0), 4.0)  # fits, untouched
    # 1 m of room at aspect 0.5 means at most 2 m long.
    assert approx(wide.fitted_length(4.0, 1.0), 2.0)


def test_scaling_down_to_fit_keeps_the_shape():
    decal = get("arrow_straight")
    small = decal.placed(Vec2(0.0, 0.0), Vec2(0.0, 1.0), 1.0)
    large = decal.placed(Vec2(0.0, 0.0), Vec2(0.0, 1.0), 3.0)
    for a, b in zip(small[0], large[0]):
        assert_vec(b, a * 3.0)
