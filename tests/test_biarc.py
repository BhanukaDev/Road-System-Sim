"""Blending two directed points with a pair of tangent arcs.

The contract is four exact facts: it starts where it was told, pointing where it
was told, and likewise at the other end. Everything a junction kerb needs -
meeting a carriageway without a kink, bowing by however much the two headings
disagree - follows from those, so they are asserted at `EXACT` rather than
"looks about right".

The fifth is tangent continuity at the joint between the two arcs, which is what
makes the pair a curve rather than two arcs that happen to touch.
"""

from __future__ import annotations

import math

from roadsim.geometry import ArcSegment, LineSegment, Vec2, biarc

from .conftest import EXACT, assert_vec

CASES = [
    ("right angle", Vec2(0.0, 0.0), Vec2(1.0, 0.0), Vec2(20.0, 20.0), Vec2(0.0, 1.0)),
    (
        "shallow gore",
        Vec2(0.0, 0.0),
        Vec2(1.0, 0.0),
        Vec2(60.0, 6.0),
        Vec2(0.9945, 0.1045),
    ),
    ("s bend", Vec2(0.0, 0.0), Vec2(1.0, 0.0), Vec2(30.0, 8.0), Vec2(1.0, 0.0)),
    ("hairpin", Vec2(0.0, 0.0), Vec2(1.0, 0.0), Vec2(-4.0, 9.0), Vec2(-1.0, 0.0)),
    ("backwards", Vec2(3.0, -2.0), Vec2(-0.6, 0.8), Vec2(-14.0, 5.0), Vec2(-1.0, 0.0)),
]


def each_case():
    for name, p0, t0, p1, t1 in CASES:
        yield name, p0, t0.normalized(), p1, t1.normalized()


def test_a_blend_meets_both_ends_exactly():
    for name, p0, t0, p1, t1 in each_case():
        path = biarc(p0, t0, p1, t1)
        assert path is not None, name
        assert_vec(path.start.position, p0)
        assert_vec(path.end.position, p1)
        assert_vec(path.start.tangent, t0)
        assert_vec(path.end.tangent, t1)


def test_the_two_arcs_share_a_tangent_where_they_meet():
    """Not just a shared point - a kink there is a kink in the kerb."""
    for name, p0, t0, p1, t1 in each_case():
        path = biarc(p0, t0, p1, t1)
        assert path is not None, name
        if len(path.pieces) < 2:
            continue
        join = path.piece_starts[1]
        before = path.pieces[0].sample(path.pieces[0].length).tangent
        after = path.pieces[1].sample(0.0).tangent
        assert_vec(before, after)
        first_end = path.pieces[0].sample(path.pieces[0].length).position
        assert_vec(first_end, path.pieces[1].sample(0.0).position)
        assert join > 0.0


def test_two_arcs_are_enough_and_no_more():
    for name, p0, t0, p1, t1 in each_case():
        path = biarc(p0, t0, p1, t1)
        assert 1 <= len(path.pieces) <= 2, name


def test_points_already_in_line_get_a_straight_not_a_vast_arc():
    """An arc of radius 1e12 is a straight with its precision thrown away - the
    start angle of a circle that big carries no useful digits at all."""
    path = biarc(Vec2(0.0, 0.0), Vec2(1.0, 0.0), Vec2(25.0, 0.0), Vec2(1.0, 0.0))
    assert [type(piece) for piece in path.pieces] == [LineSegment]
    assert abs(path.length - 25.0) <= EXACT


def test_equal_turning_is_what_makes_the_nose_symmetric():
    """A gore nose is symmetric about the bisector of the two headings, and that
    is a property of the *equal-chord* biarc specifically: each arc turns half of
    the total deflection, so neither end does all the work."""
    p0, t0 = Vec2(0.0, 0.0), Vec2(1.0, 0.0)
    p1, t1 = Vec2(40.0, 12.0), Vec2(math.cos(0.6), math.sin(0.6))
    path = biarc(p0, t0, p1, t1)
    sweeps = [piece.sweep for piece in path.pieces if isinstance(piece, ArcSegment)]
    assert len(sweeps) == 2
    assert abs(sum(sweeps) - 0.6) <= 1e-9


def test_coincident_points_have_no_blend():
    assert biarc(Vec2(5.0, 5.0), Vec2(1.0, 0.0), Vec2(5.0, 5.0), Vec2(0.0, 1.0)) is None
