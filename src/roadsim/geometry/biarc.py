"""Joining two directed points with a pair of tangent circular arcs.

`corner_fillet` rounds a corner that *exists* - two straights that cross, and an
arc cut into the crossing. A junction mouth is the other problem: the two points
to be joined are already fixed (each is where a road's kerb stops), each already
has a direction it must leave in, and there is generally no single arc through
both. A chord between them is what a triangular gore looks like on screen, and a
fillet solved at the kerbs' apex floats away from the mouths as soon as anything
- a half-width floor, a budget clamp - moves a mouth off that apex.

A biarc solves exactly that: the shortest pair of arcs meeting tangentially at a
joint point, matching position *and* direction at both ends. Two arcs is the
minimum that can do it, which is why this is the standard construction rather
than a spline - and arcs are the only curve this project will offset exactly
(D1), so a kerb blended this way carries its pavement band for free.

The construction is the equal-chord biarc: both arcs get the same tangent length
`d` from their own endpoint, which makes the joint point
`((p0 + d*t0) + (p1 - d*t1)) / 2` and leaves one quadratic to solve. Equal
lengths are what keeps the result symmetric - the "bell" a real gore nose has,
rather than one arc doing all the turning and the other going along for the ride.
"""

from __future__ import annotations

import math

from .arc import ArcSegment
from .curve import Curve
from .line import LineSegment
from .path import Path
from .vec import Vec2

EPS = 1e-9
STRAIGHT_EPS = 1e-7
"""Relative sagitta below which a piece is a straight, not an enormous arc.

Scaled by the chord, so it is the same *shape* test at every size - an absolute
metre threshold would call a 200 m sweeping curve straight and a 2 m one bent."""


def biarc(p0: Vec2, t0: Vec2, p1: Vec2, t1: Vec2) -> Path | None:
    """The tangent-continuous blend leaving `p0` along `t0` and arriving at `p1`
    along `t1`.

    Directions are directions of *travel*: `t0` points away from `p0` into the
    blend, `t1` points away from `p1` in the same sense - so a road arriving at
    a junction and another leaving it hand in their own forward tangents and the
    result runs from one to the other.

    `None` when there is nothing to build: the two points coincide, or the
    tangents are anti-parallel along the chord, which asks for a reversal no
    pair of arcs can make.
    """
    chord = p1 - p0
    if chord.length_sq <= EPS * EPS:
        return None
    t0, t1 = t0.normalized(), t1.normalized()

    d = _tangent_length(chord, t0, t1)
    if d is None:
        return None
    if d is _STRAIGHT:
        return Path.of(LineSegment(p0, p1))

    joint = ((p0 + t0 * d) + (p1 - t1 * d)) * 0.5
    # The second arc is built backwards from `p1` and then reversed, so the
    # tangent it matches exactly is the one the caller asked for at `p1`. Built
    # forwards it would inherit whatever the joint tangent happened to be and
    # leave the error at the end that has a road attached to it.
    first = _piece(p0, t0, joint)
    second = _piece(p1, -t1, joint)
    pieces = [c for c in (first, None if second is None else second.reversed()) if c]
    if not pieces:
        return None
    return Path(tuple(pieces))


_STRAIGHT = object()
"""Sentinel: the two points already line up, so no arc is wanted at all."""


def _tangent_length(chord: Vec2, t0: Vec2, t1: Vec2) -> float | None | object:
    """Solve `a d^2 + b d + c = 0` for the equal-chord biarc's tangent length."""
    turn = t0 + t1
    a = 2.0 * (1.0 - t0.dot(t1))
    b = 2.0 * chord.dot(turn)
    c = -chord.length_sq

    if a <= EPS:
        # Parallel tangents. Either the whole thing is a straight run, or it is
        # the S-bend between two parallel roads, where the quadratic is linear.
        if abs(chord.cross(t0)) <= STRAIGHT_EPS * chord.length:
            return _STRAIGHT
        if abs(b) <= EPS:
            return None
        d = -c / b
    else:
        disc = b * b - 4.0 * a * c
        if disc < 0.0:
            return None
        d = (-b + math.sqrt(disc)) / (2.0 * a)
    return d if d > EPS else None


def _piece(start: Vec2, direction: Vec2, end: Vec2) -> Curve | None:
    """The single arc leaving `start` along `direction` and reaching `end`.

    Its centre has to sit on the normal at `start`, so the radius falls straight
    out of the chord and how far off that chord's own line `end` lies. A chord
    that lies *on* the line is a straight, not an arc of near-infinite radius -
    `ArcSegment` would take the huge radius quite happily and then lose all its
    precision in `start_angle`.
    """
    chord = end - start
    length_sq = chord.length_sq
    if length_sq <= EPS * EPS:
        return None
    height = chord.dot(direction.rot90())
    if abs(height) <= STRAIGHT_EPS * math.sqrt(length_sq):
        return LineSegment(start, end)
    return ArcSegment.from_tangent_points(
        start, direction, end, abs(length_sq / (2.0 * height))
    )
