"""Starting or ending a *new* road on an existing road's lane (D21).

`editor/lane_connect.py` answers the same question for two roads that already
exist: merge the nodes, then solve a datum so the two chosen lanes line up.
A road being drawn has it easier in one respect and harder in another.

Easier: there is nothing to merge. The stroke simply ends at the node the lane
handle belongs to, which `tools/draw_road.py:_endpoint` already knows how to
do for any `NODE` snap - a lane handle is a node snap that also remembers
*which* lane was pointed at.

Harder: at the moment the user clicks the first point, the new road has no
direction yet, so there is no frame to measure a lane offset in and nothing to
pair with. So the pairing is deferred to commit, where the fitted path exists
and both ends can be answered by the same function.

**Which lane pairs with which.** The picked handle is resolved to a lateral
offset `t` in the *new* road's own end frame - a pure world-space projection,
so the four grab/drop orientations `editor/lane_connect.py` has to reason
about collapse into one case with no flip term, the same way `D18` makes a
lane drag flip-free. The new road's own lane and edge offsets are then
searched for the nearest to `t`, and the datum shifts the profile by the
difference. Nearest, rather than same-index: the two roads generally have
different lane counts - a 2-lane joining a 4-lane is the whole point - so an
index means nothing across them, whereas "the lane that already almost lines
up" means the same thing whatever the two profiles are.
"""

from __future__ import annotations

from ..geometry import Path
from ..road.lane_handle import LaneHandle
from ..road.profile import RoadProfile


def lane_candidates(profile: RoadProfile) -> tuple[float, ...]:
    """Every offset in `profile` a new road can be pinned by - lane centres and
    the edges between them, exactly the set `road/lane_handle.py` publishes at
    a node, so what the user can aim at and what can be matched are one list."""
    return tuple(profile.lane_center(k) for k in profile.indices()) + profile.edges


def datum_for_lane_target(
    profile: RoadProfile, path: Path, at_a: bool, target: LaneHandle
) -> float:
    """The datum that puts `profile`'s nearest lane onto `target`.

    `at_a` says which end of `path` meets the target, so the frame - and with
    it the sign of every offset - comes from the road's own direction of
    travel rather than from the target's.
    """
    frame = path.sample(0.0 if at_a else path.length)
    t = (target.position - frame.position).dot(frame.normal)
    own = min(lane_candidates(profile), key=lambda offset: abs(offset - t))
    return profile.datum + (t - own)


def profile_for_lane_ends(
    profile: RoadProfile,
    path: Path,
    start: LaneHandle | None,
    end: LaneHandle | None,
) -> RoadProfile:
    """`profile`, shifted to honour whichever end was drawn onto a lane.

    A profile carries **one** datum and a road has two ends, so a stroke that
    starts on one road's lane and finishes on another's cannot satisfy both -
    the lanes would have to converge along the road, which is a taper, not a
    datum (`road/transition.py` is where that lives, and it needs two
    segments). The start wins: it is the end the user deliberately began from,
    and the end they finish on is the one they can still see.
    """
    target = start if start is not None else end
    if target is None:
        return profile
    return profile.with_datum(
        datum_for_lane_target(profile, path, target is start, target)
    )
