"""Is this network, as it now stands, one that can honestly be drawn?

The editor asks this of a *ghost* - a copy of the network with a proposed
change already applied and rebuilt (`editor/ghost.py`) - so that a preview can
turn red before the click rather than a commit being refused after it. Nothing
here knows about tools, snaps or the cursor: it reads the model's own verdicts
and adds the one thing the model cannot say about itself yet.

Two of the three questions are answered by flags the model already carries.
`RoadSegment.is_broken` says a road was eaten by its junctions or bent tighter
than its own width allows; `Junction.is_degenerate` says a node has no honest
kerb geometry. Reusing them, rather than re-deriving a parallel rule set, is
what keeps "the preview went red" and "the road drew as an error" the same
event - a preview that passed a rule the renderer then failed would be worse
than no preview.

The third question - does the new road cross another without meeting it at a
node - is the one gap the model has until step 6 of M3 lands crossing
detection. Today two roads can be drawn through each other and nothing forms
where they cross, which is not a junction in the wrong place but no junction at
all. Until a crossing *creates* a node, drawing one is refused here, at the
one place that already knows what a crossing is: `geometry/intersect.py`.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..geometry import Vec2
from ..geometry.intersect import path_intersections, path_self_intersections
from .network import RoadNetwork
from .segment import RoadSegment

END_EPS = 1e-6
"""Metres. A hit this close to the end both paths share is the two roads
meeting at their node, which is the whole point, not a crossing."""


@dataclass(frozen=True, slots=True)
class Problem:
    """One reason a network cannot be built as it stands, and where.

    `position` is the point worth showing the user - the crossing, or the
    offending road's midpoint - so the overlay can put the words next to the
    thing rather than in a corner. `None` when there is no one place.
    """

    reason: str
    position: Vec2 | None = None


def check(
    network: RoadNetwork,
    segment_ids: frozenset[int],
    node_ids: frozenset[int],
    new_segment_ids: frozenset[int] = frozenset(),
) -> Problem | None:
    """The first problem among the parts of `network` a change touched.

    `segment_ids` and `node_ids` scope the question to what changed: a network
    that already had a broken road somewhere else should not turn every new
    preview red for it. `new_segment_ids` are the roads that did not exist
    before the change - the only ones asked whether they cross something,
    since an existing road crossing another is not this change's doing.

    Order is by how directly the user can act on it: a road too tight or too
    short is fixed by moving the cursor; a degenerate junction by changing the
    approach; a crossing by ending on the road instead.
    """
    for sid in sorted(segment_ids):
        segment = network.segments.get(sid)
        if segment is None:
            continue
        if segment.is_degenerate:
            return Problem(
                "curve too tight for this road's width", _midpoint(segment)
            )
        if segment.is_too_short:
            return Problem("no road left between its junctions", _midpoint(segment))
    for nid in sorted(node_ids):
        junction = network.junctions.get(nid)
        if junction is not None and junction.is_degenerate:
            return Problem(
                "roads meet too shallowly to join here - join further from the"
                " end of the road, or at a steeper angle",
                junction.position,
            )
    for sid in sorted(new_segment_ids):
        segment = network.segments.get(sid)
        if segment is None:
            continue
        problem = crossing_problem(network, segment)
        if problem is not None:
            return problem
    return None


def crossing_problem(network: RoadNetwork, segment: RoadSegment) -> Problem | None:
    """Where `segment` crosses itself or another road without a node there.

    A road that shares a node with `segment` legitimately meets it at that
    node, so a hit within `END_EPS` of the shared end on *both* paths is
    skipped; any other hit between the two - a loop folding back over its own
    root, a gore whose arms cross again downstream - is a real crossing.
    """
    hits = path_self_intersections(segment.path)
    if hits:
        return Problem("road crosses itself", hits[0].point)
    for other in network.segments.values():
        if other.id == segment.id:
            continue
        shared = {segment.node_a, segment.node_b} & {other.node_a, other.node_b}
        for hit in path_intersections(segment.path, other.path):
            if shared and _at_shared_node(network, segment, other, shared, hit):
                continue
            return Problem("crosses a road - end on it instead", hit.point)
    return None


def _at_shared_node(
    network: RoadNetwork,
    a: RoadSegment,
    b: RoadSegment,
    shared: set[int],
    hit,
) -> bool:
    """Is this hit the two roads meeting at a node they both end on?"""
    for nid in shared:
        node = network.nodes.get(nid)
        if node is None:
            continue
        if _near_end(a, nid, hit.s_a) and _near_end(b, nid, hit.s_b):
            return True
    return False


def _near_end(segment: RoadSegment, node_id: int, s: float) -> bool:
    if segment.node_a == node_id and s <= END_EPS:
        return True
    if segment.node_b == node_id and s >= segment.path.length - END_EPS:
        return True
    return False


def _midpoint(segment: RoadSegment) -> Vec2:
    return segment.path.sample(segment.path.length / 2.0).position
