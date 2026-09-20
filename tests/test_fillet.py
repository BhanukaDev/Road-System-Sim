"""Rounding one corner. The whole of D1's bargain in one function.

`tests/test_fitting.py` already covers what a filleted *path* looks like, and it
passes unchanged now that `fit_polyline` delegates here - which is the proof the
extraction changed no behaviour. What this file adds is the guarantee those tests
can only imply: the arc is exactly tangent to both legs, and the clamping is
honest about the room it was given.
"""

from __future__ import annotations

import math

from roadsim.geometry import Vec2, corner_fillet, deflection
from roadsim.geometry.fillet import MIN_RADIUS

from .conftest import EXACT, approx, assert_vec

RIGHT_ANGLE = (Vec2(1.0, 0.0), Vec2(0.0, 1.0))
"""Arriving east, leaving north: a 90 degree left turn."""


def test_deflection_measures_the_turn():
    assert approx(deflection(Vec2(1.0, 0.0), Vec2(1.0, 0.0)), 0.0)
    assert approx(deflection(Vec2(1.0, 0.0), Vec2(0.0, 1.0)), math.pi / 2.0)
    assert approx(deflection(Vec2(1.0, 0.0), Vec2(-1.0, 0.0)), math.pi)


def test_deflection_survives_a_dot_product_past_one():
    """Rounding can push the dot product of two unit vectors outside [-1, 1], and
    `acos` raises on that rather than shrugging."""
    almost = Vec2(1.0, 0.0)
    assert approx(deflection(almost, almost), 0.0)


def test_the_arc_is_exactly_tangent_to_both_legs():
    """The assertion the whole kernel rests on: tangency is closed-form, so it is
    exact, so a lane edge offset from it is exact too."""
    corner = Vec2(0.0, 0.0)
    into, out_of = RIGHT_ANGLE
    fillet = corner_fillet(corner, into, out_of, 10.0)

    assert fillet is not None
    assert_vec(fillet.arc.start.position, fillet.entry)
    assert_vec(fillet.arc.end.position, fillet.exit)
    # Tangent directions match the legs exactly.
    assert approx(fillet.arc.start.tangent.cross(into), 0.0)
    assert approx(fillet.arc.end.tangent.cross(out_of), 0.0)
    # And the centre is exactly one radius from both legs.
    assert approx(fillet.arc.center.distance_to(fillet.entry), fillet.radius)
    assert approx(fillet.arc.center.distance_to(fillet.exit), fillet.radius)


def test_a_right_angle_pulls_back_exactly_the_radius():
    """tan(45 degrees) is 1, so the tangent length is the radius itself - the one
    case where the arithmetic can be checked by eye."""
    fillet = corner_fillet(Vec2(0.0, 0.0), *RIGHT_ANGLE, 10.0)
    assert approx(fillet.radius, 10.0)
    assert approx(fillet.tangent_length(Vec2(0.0, 0.0)), 10.0)
    assert_vec(fillet.entry, Vec2(-10.0, 0.0))
    assert_vec(fillet.exit, Vec2(0.0, 10.0))


def test_the_sharper_the_turn_the_more_straight_it_eats():
    """The pull-back is `radius * tan(turn / 2)`, so at a fixed radius a hairpin
    needs a far longer approach than a gentle bend. This is why a junction corner
    has to be clamped against the room its arms actually have, and why clamping
    bites first on exactly the sharp corners that most want rounding."""
    corner = Vec2(0.0, 0.0)
    east = Vec2(1.0, 0.0)
    pull_backs = [
        corner_fillet(corner, east, east.rotated(math.radians(turn)), 10.0).tangent_length(
            corner
        )
        for turn in (20.0, 60.0, 90.0, 140.0)
    ]
    assert pull_backs == sorted(pull_backs)
    assert approx(pull_backs[2], 10.0)  # 90 degrees: tan(45) is 1


def test_a_collinear_corner_is_not_a_corner():
    assert corner_fillet(Vec2(0.0, 0.0), Vec2(1.0, 0.0), Vec2(1.0, 0.0), 10.0) is None


def test_a_full_reversal_cannot_be_filleted():
    """No arc joins a road to itself heading back the way it came."""
    assert corner_fillet(Vec2(0.0, 0.0), Vec2(1.0, 0.0), Vec2(-1.0, 0.0), 10.0) is None


def test_the_room_given_caps_the_radius():
    corner = Vec2(0.0, 0.0)
    roomy = corner_fillet(corner, *RIGHT_ANGLE, 10.0)
    cramped = corner_fillet(corner, *RIGHT_ANGLE, 10.0, room_in=3.0, room_out=50.0)

    assert approx(roomy.radius, 10.0)
    assert approx(cramped.radius, 3.0)
    assert approx(cramped.tangent_length(corner), 3.0)


def test_the_tighter_side_is_the_one_that_binds():
    corner = Vec2(0.0, 0.0)
    left = corner_fillet(corner, *RIGHT_ANGLE, 10.0, room_in=2.0, room_out=40.0)
    right = corner_fillet(corner, *RIGHT_ANGLE, 10.0, room_in=40.0, room_out=2.0)
    assert approx(left.radius, right.radius)


def test_a_corner_squeezed_below_the_minimum_is_left_as_a_kink():
    """Better an honest visible kink than a silent arc of no radius at all."""
    squeezed = corner_fillet(
        Vec2(0.0, 0.0), *RIGHT_ANGLE, 10.0, room_in=MIN_RADIUS / 2.0
    )
    assert squeezed is None


def test_no_room_at_all_means_no_fillet():
    assert corner_fillet(Vec2(0.0, 0.0), *RIGHT_ANGLE, 10.0, room_in=0.0) is None


def test_a_right_turn_fillets_the_same_way_as_a_left_one():
    """Only the arc's direction should differ. A sign error here shows up as
    asymmetric roads, which is much harder to spot than a broken one."""
    corner = Vec2(0.0, 0.0)
    left = corner_fillet(corner, Vec2(1.0, 0.0), Vec2(0.0, 1.0), 10.0)
    right = corner_fillet(corner, Vec2(1.0, 0.0), Vec2(0.0, -1.0), 10.0)

    assert approx(left.radius, right.radius)
    assert approx(left.tangent_length(corner), right.tangent_length(corner))
    assert left.arc.turn_sign > 0.0 and right.arc.turn_sign < 0.0
    assert_vec(left.entry, right.entry)


def test_the_arc_length_is_the_radius_times_the_turn():
    """Arc length, not chord length - the parameterisation everything downstream
    relies on (D2)."""
    fillet = corner_fillet(Vec2(0.0, 0.0), *RIGHT_ANGLE, 10.0)
    assert approx(fillet.arc.length, 10.0 * math.pi / 2.0, EXACT)
