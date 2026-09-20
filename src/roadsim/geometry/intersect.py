"""Where two curves cross. Closed-form, exact, no iteration.

This is the foundation under four separate features - detecting that a new road
crosses an existing one, refusing a road that overlaps itself, trimming a junction
against the real kerbs instead of straight tangent rays, and rounding a junction
corner - so it is built once, alone, and tested harder than any of them.

Every hit is reported as an arc length on **both** curves, because that is what
the callers want: a crossing is a place to split a road, and a split needs `s`.
That the point agrees from either parameterisation is the module's central
invariant, asserted to machine precision.

Two traps, both of which produce wrong junctions rather than obvious failures:

* **Containment goes through `ArcSegment.s_at_angle`, never `project`.** `project`
  clamps to the nearer endpoint, so it answers "yes, at the corner" for points the
  arc never reaches.
* **A hit on a join is found twice**, once from each piece that meets there, so
  `path_intersections` dedupes. Splitting a road twice at one point leaves a
  zero-length segment.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .aabb import Aabb, curve_bounds, path_bounds
from .arc import ArcSegment
from .curve import Curve
from .line import LineSegment
from .path import Path
from .vec import Vec2

PARALLEL_EPS = 1e-9
"""Below this cross product two directions count as parallel and do not cross.

Directions are unit vectors, so the cross product *is* the sine of the angle
between them: 1e-9 is about a millionth of a degree. Tighter would be false
economy - two kerbs a nanoradian apart cross somewhere astronomically far away,
and calling that an intersection is worse than calling them parallel."""
TOUCH_EPS = 1e-9
"""Slack when deciding a hit is still on a finite curve. One nanometre: wide
enough for a hit that lands exactly on an endpoint to survive rounding, far too
narrow to invent a crossing that is not there."""
JOIN_EPS = 1e-6
"""Two hits closer than this, on both curves, are one hit found twice."""


@dataclass(frozen=True, slots=True)
class Hit:
    point: Vec2
    s_a: float
    """Arc length along the first curve."""
    s_b: float
    """Arc length along the second."""

    def swapped(self) -> Hit:
        return Hit(self.point, self.s_b, self.s_a)

    def shifted(self, da: float, db: float) -> Hit:
        """The same hit expressed on two longer curves - a piece inside a path."""
        return Hit(self.point, self.s_a + da, self.s_b + db)


# -- rays ------------------------------------------------------------------


def ray_ray(p: Vec2, u: Vec2, q: Vec2, v: Vec2) -> Vec2 | None:
    """Where two *infinite* lines cross, or `None` when they are parallel.

    Deliberately unbounded: junction trimming asks where two kerbs would meet if
    they ran on, which is a different question from where they do meet.
    """
    denom = u.cross(v)
    if abs(denom) < PARALLEL_EPS:
        return None
    return p + u * ((q - p).cross(v) / denom)


# -- curve pairs -----------------------------------------------------------


def line_line(a: LineSegment, b: LineSegment) -> tuple[Hit, ...]:
    """One rational solve. Parallel lines report nothing, collinear included."""
    da, db = a.direction, b.direction
    denom = da.cross(db)
    if abs(denom) < PARALLEL_EPS:
        return ()
    w = b.p0 - a.p0
    s_a = w.cross(db) / denom
    s_b = w.cross(da) / denom
    if not (_on(s_a, a.length) and _on(s_b, b.length)):
        return ()
    return (Hit(a.sample(s_a).position, _clamp(s_a, a.length), _clamp(s_b, b.length)),)


def line_arc(a: LineSegment, b: ArcSegment) -> tuple[Hit, ...]:
    """Solved through the perpendicular foot and half-chord.

    Not the general quadratic: the foot form keeps its precision at grazing
    incidence, which is exactly the case a junction between two shallow roads
    lands on.
    """
    direction = a.direction
    to_center = b.center - a.p0
    foot = to_center.dot(direction)
    offset = to_center.cross(direction)  # signed distance, line to centre
    gap = b.radius * b.radius - offset * offset
    if gap < -TOUCH_EPS:
        return ()

    half_chord = math.sqrt(max(gap, 0.0))
    candidates = (
        (foot,) if half_chord <= TOUCH_EPS else (foot - half_chord, foot + half_chord)
    )

    hits: list[Hit] = []
    for s_a in candidates:
        if not _on(s_a, a.length):
            continue
        point = a.sample(_clamp(s_a, a.length)).position
        s_b = b.s_at_angle((point - b.center).angle, TOUCH_EPS / max(b.radius, TOUCH_EPS))
        if s_b is None:
            continue
        hits.append(Hit(point, _clamp(s_a, a.length), s_b))
    return tuple(hits)


def arc_line(a: ArcSegment, b: LineSegment) -> tuple[Hit, ...]:
    return tuple(hit.swapped() for hit in line_arc(b, a))


def arc_arc(a: ArcSegment, b: ArcSegment) -> tuple[Hit, ...]:
    """Circle-circle through the radical line, then both sweeps.

    Coincident circles have infinitely many hits, which no tuple can say, so they
    report nothing here and `arcs_overlap` answers that question instead. A
    silent `()` for a coincident pair is a hole a validator would fall through.
    """
    between = b.center - a.center
    distance = between.length
    if distance < TOUCH_EPS:
        return ()  # concentric: either coincident or never touching
    if distance > a.radius + b.radius + TOUCH_EPS:
        return ()
    if distance < abs(a.radius - b.radius) - TOUCH_EPS:
        return ()  # one circle strictly inside the other

    along = (a.radius * a.radius - b.radius * b.radius + distance * distance) / (
        2.0 * distance
    )
    height_sq = a.radius * a.radius - along * along
    height = math.sqrt(max(height_sq, 0.0))
    base = a.center + between * (along / distance)
    sideways = between.rot90() * (height / distance)

    points = (base,) if height <= TOUCH_EPS else (base + sideways, base - sideways)
    hits: list[Hit] = []
    for point in points:
        s_a = a.s_at_angle((point - a.center).angle, TOUCH_EPS / a.radius)
        s_b = b.s_at_angle((point - b.center).angle, TOUCH_EPS / b.radius)
        if s_a is None or s_b is None:
            continue
        hits.append(Hit(point, s_a, s_b))
    return tuple(hits)


def arcs_overlap(a: ArcSegment, b: ArcSegment) -> bool:
    """True when these arcs lie on one circle and their sweeps overlap.

    The case `arc_arc` cannot express. Two roads sharing a curve are not crossing
    at a point, they are lying on top of each other, and that is a different
    answer for a validator to give.
    """
    if a.center.distance_to(b.center) > TOUCH_EPS:
        return False
    if abs(a.radius - b.radius) > TOUCH_EPS:
        return False
    slack = TOUCH_EPS / a.radius
    return (
        b.contains_angle(a.start_angle, slack)
        or b.contains_angle(a.start_angle + a.sweep, slack)
        or a.contains_angle(b.start_angle, slack)
        or a.contains_angle(b.start_angle + b.sweep, slack)
    )


_PAIRS = {
    (LineSegment, LineSegment): line_line,
    (LineSegment, ArcSegment): line_arc,
    (ArcSegment, LineSegment): arc_line,
    (ArcSegment, ArcSegment): arc_arc,
}
"""One entry per ordered pair of curve types. A new `Curve` subclass - D1's
escape hatch for splines - registers here instead of branching anything."""


def curve_curve(a: Curve, b: Curve) -> tuple[Hit, ...]:
    solver = _PAIRS.get((type(a), type(b)))
    if solver is not None:
        return solver(a, b)
    swapped = _PAIRS.get((type(b), type(a)))
    if swapped is not None:
        return tuple(hit.swapped() for hit in swapped(b, a))
    raise TypeError(
        f"no intersection known for {type(a).__name__} and {type(b).__name__}"
    )


# -- paths -----------------------------------------------------------------


def path_intersections(p: Path, q: Path) -> tuple[Hit, ...]:
    """Every crossing between two paths, as global arc lengths, sorted by `s_a`.

    Rejects piece pairs on their bounds first, then dedupes: a hit sitting on a
    join belongs to both pieces that meet there and would otherwise be reported
    twice, which downstream becomes two splits a hair apart and a segment of
    almost no length between them.
    """
    hits: list[Hit] = []
    for piece_a, start_a, box_a in _pieces(p):
        for piece_b, start_b, box_b in _pieces(q):
            if not box_a.intersects(box_b):
                continue
            for hit in curve_curve(piece_a, piece_b):
                hits.append(hit.shifted(start_a, start_b))
    return _deduped(hits)


def path_self_intersections(p: Path) -> tuple[Hit, ...]:
    """Where a path crosses itself - a loop closing, or a road folded over.

    Neighbouring pieces are skipped: they *do* meet, at the join they share, and
    that is the path being continuous rather than the path being broken.
    """
    pieces = _pieces(p)
    hits: list[Hit] = []
    for i, (piece_a, start_a, box_a) in enumerate(pieces):
        for j in range(i + 2, len(pieces)):
            piece_b, start_b, box_b = pieces[j]
            if not box_a.intersects(box_b):
                continue
            for hit in curve_curve(piece_a, piece_b):
                hits.append(hit.shifted(start_a, start_b))
    return _deduped(hits)


def path_touches(p: Path, q: Path) -> bool:
    """Do these two paths meet at all? Stops at the first hit it finds."""
    if not path_bounds(p).intersects(path_bounds(q)):
        return False
    for piece_a, _, box_a in _pieces(p):
        for piece_b, _, box_b in _pieces(q):
            if box_a.intersects(box_b) and curve_curve(piece_a, piece_b):
                return True
    return False


# -- helpers ---------------------------------------------------------------


def _pieces(path: Path) -> list[tuple[Curve, float, Aabb]]:
    return [
        (piece, start, curve_bounds(piece))
        for piece, start in zip(path.pieces, path.piece_starts)
    ]


def _deduped(hits: list[Hit]) -> tuple[Hit, ...]:
    kept: list[Hit] = []
    for hit in sorted(hits, key=lambda h: (h.s_a, h.s_b)):
        if any(
            abs(hit.s_a - seen.s_a) <= JOIN_EPS and abs(hit.s_b - seen.s_b) <= JOIN_EPS
            for seen in kept
        ):
            continue
        kept.append(hit)
    return tuple(kept)


def _on(s: float, length: float) -> bool:
    return -TOUCH_EPS <= s <= length + TOUCH_EPS


def _clamp(s: float, length: float) -> float:
    return min(max(s, 0.0), length)
