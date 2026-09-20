"""Axis-aligned bounds. The cheap "no" in front of every expensive question.

Intersection, collision and crossing queries are all quadratic in the number of
pieces if you ask them honestly, and nearly free if you reject the pairs that
cannot possibly touch. That rejection is only sound if a box is a true **bound**,
so the arc box here is closed-form rather than sampled: a sampled box misses the
bulge between samples, and a box that is occasionally too small turns into a
crossing the editor silently fails to notice.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .arc import ArcSegment
from .curve import Curve
from .line import LineSegment
from .path import Path
from .vec import Vec2

AXIS_ANGLES: tuple[float, ...] = (
    0.0,
    math.pi / 2.0,
    math.pi,
    3.0 * math.pi / 2.0,
)
"""Where a circle reaches its extreme x and y. An arc's box needs whichever of
these its sweep actually covers, plus its two endpoints."""


@dataclass(frozen=True, slots=True)
class Aabb:
    min: Vec2
    max: Vec2

    @staticmethod
    def of(*points: Vec2) -> Aabb:
        if not points:
            raise ValueError("an Aabb needs at least one point")
        xs = [p.x for p in points]
        ys = [p.y for p in points]
        return Aabb(Vec2(min(xs), min(ys)), Vec2(max(xs), max(ys)))

    @property
    def center(self) -> Vec2:
        return (self.min + self.max) * 0.5

    @property
    def size(self) -> Vec2:
        return self.max - self.min

    def expanded(self, d: float) -> Aabb:
        """Grown by `d` on every side. Negative shrinks, which is how a test
        proves a box is tight rather than merely sound."""
        return Aabb(self.min - Vec2(d, d), self.max + Vec2(d, d))

    def union(self, other: Aabb) -> Aabb:
        return Aabb(
            Vec2(min(self.min.x, other.min.x), min(self.min.y, other.min.y)),
            Vec2(max(self.max.x, other.max.x), max(self.max.y, other.max.y)),
        )

    def intersects(self, other: Aabb) -> bool:
        """Touching counts. A rejection test must never reject a real contact."""
        return (
            self.min.x <= other.max.x
            and other.min.x <= self.max.x
            and self.min.y <= other.max.y
            and other.min.y <= self.max.y
        )

    def contains(self, p: Vec2) -> bool:
        return (
            self.min.x <= p.x <= self.max.x and self.min.y <= p.y <= self.max.y
        )


def line_bounds(line: LineSegment) -> Aabb:
    return Aabb.of(line.p0, line.p1)


def arc_bounds(arc: ArcSegment) -> Aabb:
    """Endpoints, plus every axis extreme the sweep actually reaches.

    Closed-form, so it is exact however tight the arc: the widest point of a
    curve is where its tangent goes axis-aligned, and on a circle that is one of
    four known angles.
    """
    points = [arc.start.position, arc.end.position]
    for angle in AXIS_ANGLES:
        if arc.contains_angle(angle):
            points.append(arc.center + Vec2.from_angle(angle, arc.radius))
    return Aabb.of(*points)


_BOUNDS = {LineSegment: line_bounds, ArcSegment: arc_bounds}
"""One line per curve type. A new `Curve` subclass registers here (rule 2)."""


def curve_bounds(curve: Curve) -> Aabb:
    bounds = _BOUNDS.get(type(curve))
    if bounds is None:
        raise TypeError(f"no bounds known for {type(curve).__name__}")
    return bounds(curve)


def path_bounds(path: Path) -> Aabb:
    box = curve_bounds(path.pieces[0])
    for piece in path.pieces[1:]:
        box = box.union(curve_bounds(piece))
    return box
