"""Turning corner points into a drivable tangent-arc-tangent `Path`.

Real roads are straights joined by arcs, so that is what the editor produces.
Each interior corner gets a fillet arc of the requested radius, pulled back to a
smaller radius when the neighbouring straights are too short to hold it.

`fit_freehand` is the bridge to organic drawing: a raw mouse stroke is simplified
to corner points first, then filleted, so a hand-drawn squiggle comes out looking
like a road rather than like a squiggle.
"""

from __future__ import annotations

import math

from .arc import ArcSegment
from .curve import Curve
from .line import LineSegment
from .path import Path
from .vec import Vec2

EPS = 1e-6
MIN_RADIUS = 0.5
"""Metres. Below this a corner is left as a hard kink rather than filleted."""


def _deflection(u: Vec2, v: Vec2) -> float:
    """Angle turned between two unit directions, in [0, pi]."""
    return math.acos(min(max(u.dot(v), -1.0), 1.0))


def fit_polyline(points: list[Vec2], radius: float) -> Path:
    """Chain of straights joined by fillet arcs of (at most) `radius`."""
    pts = _dedupe(points)
    if len(pts) < 2:
        raise ValueError("need at least two distinct points to fit a path")
    if len(pts) == 2:
        return Path.of(LineSegment(pts[0], pts[1]))

    dirs = [(pts[i + 1] - pts[i]).normalized() for i in range(len(pts) - 1)]
    seg_lengths = [pts[i].distance_to(pts[i + 1]) for i in range(len(pts) - 1)]

    # Desired tangent pull-back per interior corner.
    tangents: list[float] = [0.0] * len(pts)
    angles: list[float] = [0.0] * len(pts)
    for i in range(1, len(pts) - 1):
        phi = _deflection(dirs[i - 1], dirs[i])
        angles[i] = phi
        if phi < EPS or math.pi - phi < EPS:
            continue  # collinear, or a full reversal we cannot fillet
        tangents[i] = radius * math.tan(phi / 2.0)

    _clamp_tangents(tangents, seg_lengths)

    pieces: list[Curve] = []
    cursor = pts[0]
    for i in range(1, len(pts) - 1):
        t = tangents[i]
        if t < EPS:
            continue
        r = t / math.tan(angles[i] / 2.0)
        if r < MIN_RADIUS:
            continue
        entry = pts[i] - dirs[i - 1] * t
        exit_ = pts[i] + dirs[i] * t
        _push_line(pieces, cursor, entry)
        pieces.append(ArcSegment.from_tangent_points(entry, dirs[i - 1], exit_, r))
        cursor = exit_
    _push_line(pieces, cursor, pts[-1])

    if not pieces:
        return Path.of(LineSegment(pts[0], pts[-1]))
    return Path(tuple(pieces))


def fit_freehand(points: list[Vec2], radius: float, tolerance: float = 2.0) -> Path:
    """Simplify a raw drawn stroke, then fillet it into a road-shaped path."""
    return fit_polyline(simplify(points, tolerance), radius)


def simplify(points: list[Vec2], tolerance: float) -> list[Vec2]:
    """Ramer-Douglas-Peucker. Keeps the points that carry the shape."""
    pts = _dedupe(points)
    if len(pts) < 3:
        return pts
    keep = [False] * len(pts)
    keep[0] = keep[-1] = True
    stack = [(0, len(pts) - 1)]
    while stack:
        lo, hi = stack.pop()
        if hi - lo < 2:
            continue
        chord = LineSegment(pts[lo], pts[hi])
        worst_i, worst_d = -1, tolerance
        for i in range(lo + 1, hi):
            d = pts[i].distance_to(chord.sample(chord.project(pts[i])).position)
            if d > worst_d:
                worst_i, worst_d = i, d
        if worst_i >= 0:
            keep[worst_i] = True
            stack.append((lo, worst_i))
            stack.append((worst_i, hi))
    return [p for p, k in zip(pts, keep) if k]


def _clamp_tangents(tangents: list[float], seg_lengths: list[float]) -> None:
    """Cap each fillet at half of its shorter neighbouring straight, in place.

    Halves rather than scaling a shared straight proportionally: two identical
    corners then get identical radii regardless of which end we clamp from, and
    every straight keeps some length of its own - which is the room junction
    trimming will want at each end later.
    """
    for corner in range(1, len(tangents) - 1):
        room = min(seg_lengths[corner - 1], seg_lengths[corner]) * 0.5
        tangents[corner] = min(tangents[corner], room)


def _push_line(pieces: list[Curve], a: Vec2, b: Vec2) -> None:
    if a.distance_to(b) > EPS:
        pieces.append(LineSegment(a, b))


def _dedupe(points: list[Vec2]) -> list[Vec2]:
    out: list[Vec2] = []
    for p in points:
        if not out or out[-1].distance_to(p) > EPS:
            out.append(p)
    return out
