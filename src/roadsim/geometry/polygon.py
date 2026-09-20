"""Polygon predicates. Small, closed-form, and here so nobody hand-rolls them.

A junction surface is a polygon, and the editor needs to know when the cursor is
over one - to highlight what a bulldozer would take, or to pick a junction rather
than the road running through it. Written once, in `geometry`, because "is this
point inside that ring" is not a road question.
"""

from __future__ import annotations

from collections.abc import Sequence

from .vec import Vec2

ON_EDGE_EPS = 1e-9
"""A point this close to the boundary counts as inside. A cursor exactly on a
kerb should pick the junction, not fall through it."""


def signed_area(points: Sequence[Vec2]) -> float:
    """Shoelace. Positive when the ring winds counter-clockwise (+y up, D3)."""
    if len(points) < 3:
        return 0.0
    total = 0.0
    for a, b in zip(points, (*points[1:], points[0])):
        total += a.cross(b)
    return total / 2.0


def is_ccw(points: Sequence[Vec2]) -> bool:
    return signed_area(points) > 0.0


def contains(points: Sequence[Vec2], p: Vec2) -> bool:
    """Crossing number, with the boundary counted as inside.

    The boundary is explicit rather than left to the ray test, which answers a
    point exactly on an edge according to rounding - so a cursor on a kerb would
    flicker in and out of the junction as it moved along it.
    """
    if len(points) < 3:
        return False
    if any(
        _on_segment(a, b, p)
        for a, b in zip(points, (*points[1:], points[0]))
    ):
        return True

    inside = False
    for a, b in zip(points, (*points[1:], points[0])):
        if (a.y > p.y) != (b.y > p.y):
            x = a.x + (p.y - a.y) * (b.x - a.x) / (b.y - a.y)
            if p.x < x:
                inside = not inside
    return inside


def _on_segment(a: Vec2, b: Vec2, p: Vec2) -> bool:
    span = b - a
    length = span.length
    if length < ON_EDGE_EPS:
        return a.distance_to(p) <= ON_EDGE_EPS
    along = (p - a).dot(span) / length
    if along < -ON_EDGE_EPS or along > length + ON_EDGE_EPS:
        return False
    return abs((p - a).cross(span) / length) <= ON_EDGE_EPS
