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


def is_simple(points: Sequence[Vec2]) -> bool:
    """Does this ring avoid crossing or touching itself?

    A junction surface is filled as one polygon, and a filled non-simple ring
    is not an error anyone sees - it is bowties and holes that read as a
    rendering glitch rather than as the geometry being wrong. So the ring is
    asked directly, and a caller that gets `False` flags the junction instead
    of handing the shape to a fill.

    Edges that share a vertex are skipped: meeting there is the ring being
    closed, not the ring being broken. Everything else counts, touching
    included - a ring that grazes itself has no honest inside.
    """
    n = len(points)
    if n < 3:
        return False
    for i in range(n):
        a0, a1 = points[i], points[(i + 1) % n]
        for j in range(i + 1, n):
            if j == i or (j + 1) % n == i or (i + 1) % n == j:
                continue  # neighbours in the ring, sharing a vertex by design
            if _segments_meet(a0, a1, points[j], points[(j + 1) % n]):
                return False
    return True


def _side_distance(a: Vec2, b: Vec2, p: Vec2) -> float:
    """Signed distance of `p` from the line `a -> b`, in metres.

    The raw cross product is an area, so a tolerance against it would mean
    different things for a long edge and a short one. Dividing by the edge
    length puts the test back in the units the tolerance is written in.
    """
    span = b - a
    length = span.length
    if length < ON_EDGE_EPS:
        return (p - a).length
    return (p - a).cross(span) / length


def _segments_meet(p1: Vec2, p2: Vec2, p3: Vec2, p4: Vec2) -> bool:
    d1 = _side_distance(p3, p4, p1)
    d2 = _side_distance(p3, p4, p2)
    d3 = _side_distance(p1, p2, p3)
    d4 = _side_distance(p1, p2, p4)
    if _straddles(d1, d2) and _straddles(d3, d4):
        return True  # each edge has the other's ends strictly either side
    # Collinear or grazing: an endpoint lying on the other edge is a touch.
    return (
        (abs(d1) <= ON_EDGE_EPS and _on_segment(p3, p4, p1))
        or (abs(d2) <= ON_EDGE_EPS and _on_segment(p3, p4, p2))
        or (abs(d3) <= ON_EDGE_EPS and _on_segment(p1, p2, p3))
        or (abs(d4) <= ON_EDGE_EPS and _on_segment(p1, p2, p4))
    )


def _straddles(near: float, far: float) -> bool:
    """Two signed distances strictly either side of the line they measure from."""
    return (
        abs(near) > ON_EDGE_EPS
        and abs(far) > ON_EDGE_EPS
        and (near > 0.0) != (far > 0.0)
    )
