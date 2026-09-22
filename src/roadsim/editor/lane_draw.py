"""Where a narrower road sits across a wider one it joins (D25).

Two roads of different widths meeting at a node share a centreline point and
nothing else: which of the wide road's lanes the narrow one lines up with is a
lateral offset, and that offset is the narrow road's `RoadProfile.datum`. This
module decides the offset from *where the cursor is*, not from a handle the
user has to hit.

**Arrangements.** Across a road of width `W` a road of width `w` has
`|W - w| / 2` of room either side of centre. Within that room, the offsets at
which some lane line of one road lies on some lane line of the other are the
arrangements - the kerb-hugging extremes are always among them, since a kerb
is a lane line too - and the cursor's lateral position across the wide road
picks the nearest. Equal widths have no room and no arrangements: the roads
simply centre, which is what a datum of zero means.

**Which frame.** The arrangement is chosen in the *existing* road's frame,
because that is the frame the cursor is moving in. It is applied in the *new*
road's own end frame, because a datum is measured there: the body-centre
target `centre + normal * c` is projected onto the new road's end normal. A
road leaving along the existing road's tangent gets `c` exactly; one leaving
square on gets zero, because the target is then straight ahead of it rather
than beside it - which is the right answer for a T.

**One datum, two ends, the start wins.** A profile carries one datum and a
road has two ends; a stroke that starts across one road and ends across
another cannot honour both - lanes converging along a road is a transition,
not a datum. The start is the end the user deliberately began from.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..geometry import Path, Vec2
from ..road.network import RoadNetwork
from ..road.profile import RoadProfile
from .snapping import Snap, SnapKind

_EPS = 1e-9


@dataclass(frozen=True, slots=True)
class Attachment:
    """The road a stroke's end is attached to, and the frame to measure an
    arrangement in: its centreline point there, its left normal, its profile."""

    centre: Vec2
    normal: Vec2
    profile: RoadProfile

    def lateral(self, point: Vec2) -> float:
        """Where `point` sits across the road: +left of its A -> B direction."""
        return (point - self.centre).dot(self.normal)

    def target(self, c: float) -> Vec2:
        """The world point a new body centred at arrangement `c` sits over."""
        return self.centre + self.normal * c


def same_width(a: RoadProfile, b: RoadProfile) -> bool:
    return abs(a.total_width - b.total_width) < _EPS


def attachment_for(
    network: RoadNetwork, snap: Snap | None, profile: RoadProfile
) -> Attachment | None:
    """What a road of `profile` drawn to `snap` would be arranged across.

    `None` when the snap is free, or when every road there has `profile`'s
    width - then there is nothing to arrange and the datum is zero. At a node
    with several roads the first of a different width, in id order, gives the
    frame: the normals of two roads running through a node are anti-parallel,
    so the choice only flips the sign of `c`, and `c` is chosen and applied in
    the same frame either way.
    """
    if snap is None:
        return None
    if snap.kind is SnapKind.SEGMENT:
        segment_id, s = snap.segment_hit
        segment = network.segments.get(segment_id)
        if segment is None or same_width(segment.profile, profile):
            return None
        frame = segment.path.sample(s)
        return Attachment(frame.position, frame.normal, segment.profile)
    if snap.kind is SnapKind.NODE:
        node = network.nodes.get(snap.node_id)
        if node is None:
            return None
        for segment, at_a in network.segments_at(node.id):
            if same_width(segment.profile, profile):
                continue
            frame = segment.path.sample(0.0 if at_a else segment.path.length)
            return Attachment(node.position, frame.normal, segment.profile)
    return None


def arrangements(existing: RoadProfile, new: RoadProfile) -> tuple[float, ...]:
    """Datums of `new`, in `existing`'s frame, at which a lane line of one
    lies on a lane line of the other and the narrower body lies within the
    wider. Ascending; empty when the widths match."""
    room = abs(existing.total_width - new.total_width) / 2.0
    if room < _EPS:
        return ()
    own_lines = [edge - new.datum for edge in new.edges]
    found: set[float] = set()
    for line in existing.edges:
        for own in own_lines:
            c = line - own
            if abs(c - existing.datum) <= room + _EPS:
                found.add(round(c, 9))
    return tuple(sorted(found))


def choose_arrangement(
    existing: RoadProfile, new: RoadProfile, lateral: float
) -> float | None:
    """The arrangement nearest to where the cursor is across `existing`."""
    options = arrangements(existing, new)
    if not options:
        return None
    return min(options, key=lambda c: abs(c - lateral))


def datum_for_arrangement(
    path: Path, at_a: bool, attachment: Attachment, c: float
) -> float:
    """The datum that centres the new road's body over `attachment.target(c)`
    at the `at_a` end of `path`, measured in that end's own frame."""
    frame = path.sample(0.0 if at_a else path.length)
    return (attachment.target(c) - frame.position).dot(frame.normal)


def profile_for_ends(
    profile: RoadProfile,
    path: Path,
    start: tuple[Attachment, float] | None,
    end: tuple[Attachment, float] | None,
) -> RoadProfile:
    """`profile`, shifted for whichever end is arranged across another road.
    The start wins when both are."""
    chosen = start if start is not None else end
    if chosen is None:
        return profile
    attachment, c = chosen
    return profile.with_datum(
        datum_for_arrangement(path, chosen is start, attachment, c)
    )
