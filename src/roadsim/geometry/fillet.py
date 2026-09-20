"""Rounding one corner: the tangent-arc-tangent join, on its own.

This is the whole of D1's bargain in one function. It was `fit_polyline`'s inner
loop, extracted because three callers need the same answer and must not drift
apart: fitting a drawn polyline, the editor's curve tool placing a single arc, and
a junction rounding the corner between two kerbs.

The caller decides how much straight it is willing to give up (`room_in` /
`room_out`) and this decides what arc fits. Keeping that split means the *policy*
- how generous to be with a shared straight - stays with the caller who knows
why, and the *maths* has one home.
"""

from __future__ import annotations

import math

from .arc import ArcSegment
from .vec import Vec2

EPS = 1e-6
MIN_RADIUS = 0.5
"""Metres. Below this a corner is left as a hard kink rather than filleted."""


def deflection(u: Vec2, v: Vec2) -> float:
    """Angle turned between two unit directions, in [0, pi]."""
    return math.acos(min(max(u.dot(v), -1.0), 1.0))


class Fillet:
    """An arc and the two tangent points where it leaves the straights."""

    __slots__ = ("arc", "entry", "exit")

    def __init__(self, arc: ArcSegment, entry: Vec2, exit: Vec2) -> None:
        self.arc = arc
        self.entry = entry
        self.exit = exit

    @property
    def radius(self) -> float:
        return self.arc.radius

    def tangent_length(self, corner: Vec2) -> float:
        """How far back from the corner the arc starts. What a handle measures."""
        return corner.distance_to(self.entry)

    def __repr__(self) -> str:
        return f"Fillet(r={self.arc.radius:.3f}, entry={self.entry}, exit={self.exit})"


def corner_fillet(
    corner: Vec2,
    into: Vec2,
    out_of: Vec2,
    radius: float,
    room_in: float = float("inf"),
    room_out: float = float("inf"),
) -> Fillet | None:
    """The largest arc up to `radius` that rounds `corner` within the room given.

    `into` is the unit direction arriving at the corner, `out_of` the one leaving.
    Returns `None` when there is no corner worth rounding - collinear, a full
    reversal, or a radius squeezed below `MIN_RADIUS` - and the caller leaves a
    hard kink, which is honest and visible rather than a silent near-zero arc.
    """
    phi = deflection(into, out_of)
    if phi < EPS or math.pi - phi < EPS:
        return None  # straight through, or a reversal no arc can join

    half = math.tan(phi / 2.0)
    tangent = min(radius * half, room_in, room_out)
    if tangent < EPS:
        return None

    fitted = tangent / half
    if fitted < MIN_RADIUS:
        return None

    entry = corner - into * tangent
    exit_ = corner + out_of * tangent
    return Fillet(ArcSegment.from_tangent_points(entry, into, exit_, fitted), entry, exit_)
