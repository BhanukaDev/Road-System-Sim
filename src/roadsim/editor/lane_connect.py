"""Connecting two roads by the lane one was dragged onto the other's (D20).

Aligning a node's *position* by lane (`editor/node_grab.py`) is only half of
what the user's picture asked for: the taper a joined road needs only renders
once the two segments share one real junction node, and once they do,
*position* carries no more alignment information at all - a shared point is a
shared point. What decides which lanes line up from there is each profile's
own `datum` (`road/profile.py`), so connecting two roads by a chosen lane is a
merge plus a datum, never a position by itself.
"""

from __future__ import annotations

from ..road.lane_handle import LaneHandle
from ..road.network import RoadNetwork
from .commands import Command, Composite, MergeNodes, SetProfile


def connect_by_lane(
    network: RoadNetwork, grab: LaneHandle, drop: LaneHandle
) -> Command:
    """Merge `grab`'s node into `drop`'s, then set `grab`'s own segment's
    datum so its lane lands exactly where `drop`'s does.

    The datum can only be computed from the *merged* geometry - the dragged
    segment's tangent at the shared node depends on where its near end has
    just landed, which the merge itself decides. So this runs the merge once,
    unrecorded, to read the result, then rewinds it and hands back a fresh
    `Composite` that redoes both steps as the one entry the caller applies -
    the same rewind-then-apply-once shape `MoveNodeTool.release` already uses
    for a plain drag, one level up.
    """
    merge = MergeNodes(grab.node_id, drop.node_id)
    merge.do(network)  # unrecorded: read the merged geometry, then rewind

    segment = network.segments[grab.segment_id]
    frame = segment.path.sample(0.0 if grab.at_a else segment.path.length)
    other = network.segments[drop.segment_id]
    other_frame = other.path.sample(0.0 if drop.at_a else other.path.length)
    # Two arms drawn in opposite directions have opposing normals, so a
    # "+left" offset in one's frame is "-left" in the other's - the same flip
    # `road/transition.py` resolves once, from the two normals, rather than
    # threading a sign through every comparison (D17).
    flip = -1.0 if frame.normal.dot(other_frame.normal) < 0.0 else 1.0

    new_datum = segment.profile.datum + (flip * drop.offset - grab.offset)
    new_profile = segment.profile.with_datum(new_datum)

    merge.undo(network)  # back to two separate roads - the command redoes both
    return Composite(
        [MergeNodes(grab.node_id, drop.node_id), SetProfile(grab.segment_id, new_profile)],
        label="connect road",
    )
