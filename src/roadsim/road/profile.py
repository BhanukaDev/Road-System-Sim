"""A road's cross-section: an ordered list of lanes, left to right.

Left to right is with respect to the segment's A -> B direction, and "left" is
`+offset` because `normal = tangent.rot90()` points left (D3). Lateral offsets
therefore **descend** from `edges[0]` (leftmost) to `edges[-1]` (rightmost).

Everything here is derived from `lanes` and `datum` (D4). Nothing about a
profile is a flag, so adding a lane type never adds a field.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import cached_property

from .lane import Direction, LaneSpec, LaneType


@dataclass(frozen=True)
class RoadProfile:
    name: str
    lanes: tuple[LaneSpec, ...]
    """Ordered LEFT to RIGHT of the A -> B direction."""
    datum: float = 0.0
    """Lateral shift of the whole profile, +left.

    Lets a road be widened on one side without moving its centreline - and
    therefore without moving its junctions.
    """

    def __post_init__(self) -> None:
        if not self.lanes:
            raise ValueError(f"profile {self.name!r} has no lanes")

    # -- widths and offsets ------------------------------------------------

    @cached_property
    def total_width(self) -> float:
        return sum(lane.width for lane in self.lanes)

    @cached_property
    def edges(self) -> tuple[float, ...]:
        """The n+1 lateral offsets bounding the n lanes, descending left to right."""
        offset = self.datum + self.total_width / 2.0
        out = [offset]
        for lane in self.lanes:
            offset -= lane.width
            out.append(offset)
        return tuple(out)

    @property
    def extent_left(self) -> float:
        """Distance the profile reaches to the left of the centreline."""
        return self.edges[0]

    @property
    def extent_right(self) -> float:
        return -self.edges[-1]

    @property
    def half_width(self) -> float:
        """The wider of the two extents - a junction is never narrower than this."""
        return max(self.extent_left, self.extent_right)

    def lane_bounds(self, k: int) -> tuple[float, float]:
        """(left offset, right offset) of lane `k`. Left is the larger number."""
        return self.edges[k], self.edges[k + 1]

    def lane_center(self, k: int) -> float:
        return (self.edges[k] + self.edges[k + 1]) / 2.0

    # -- composition -------------------------------------------------------

    def __len__(self) -> int:
        return len(self.lanes)

    def __iter__(self):
        return iter(self.lanes)

    def indices(self) -> range:
        return range(len(self.lanes))

    def of_type(self, *types: LaneType) -> tuple[int, ...]:
        return tuple(k for k, lane in enumerate(self.lanes) if lane.type in types)

    @cached_property
    def forward_lanes(self) -> tuple[int, ...]:
        return self._traffic_lanes(Direction.FORWARD)

    @cached_property
    def backward_lanes(self) -> tuple[int, ...]:
        return self._traffic_lanes(Direction.BACKWARD)

    @cached_property
    def is_oneway(self) -> bool:
        """Traffic flows one way only. Derived - there is no `oneway` field (D4)."""
        return bool(self.forward_lanes) != bool(self.backward_lanes)

    def _traffic_lanes(self, direction: Direction) -> tuple[int, ...]:
        return tuple(
            k
            for k, lane in enumerate(self.lanes)
            if lane.type.carries_vehicles
            and lane.direction in (direction, Direction.BOTH)
        )

    def same_section(self, other: RoadProfile) -> bool:
        """The same tarmac: identical lanes in the same order and the same
        datum, whatever the two are called. Names carry a mirror or datum
        suffix (`mirrored`, `with_datum`) that says how a profile was reached,
        not what it is, so equality of names is the wrong question when asking
        whether two road ends meet flush."""
        return self.lanes == other.lanes and abs(self.datum - other.datum) < 1e-9

    def mirrored(self) -> RoadProfile:
        """The same cross-section seen from the B -> A direction.

        Lane order reverses, travel directions flip, and the datum flips with
        them - which is exactly what an end at `node_b` sees.

        **The name has to change with them.** A save file keys its profiles by
        name, so a network holding both a profile and its mirror under one name
        writes a single entry and loads both roads as whichever won. Mirroring
        twice strips the suffix again, so `mirrored().mirrored()` is the original
        in name as well as in shape - which is what keeps a flip-and-flip-back
        round trip byte-identical.
        """
        lanes = tuple(
            LaneSpec(lane.width, lane.direction.flipped(), lane.type, lane.speed_limit)
            for lane in reversed(self.lanes)
        )
        return RoadProfile(mirror_name(self.name), lanes, -self.datum)

    def with_datum(self, datum: float) -> RoadProfile:
        """The same lanes, shifted sideways so the profile's own centre sits
        `datum` to the left of wherever it is measured from.

        Connecting two separately-drawn roads by a chosen lane (D20) is this:
        once they share one real junction node, position carries no more
        alignment information - a shared point is a shared point - so which
        lanes line up is entirely this number.

        **The name has to change with it, same reasoning as `mirrored()`.** A
        save file keys its profiles by name, and two different datums under
        one name would collide, silently keeping whichever loaded last. The
        datum is baked into the name; asking twice replaces it rather than
        compounding it, so repeated re-alignment does not walk the name off
        into nonsense.
        """
        base = datum_base_name(self.name)
        if abs(datum) < 1e-9:
            return RoadProfile(base, self.lanes, 0.0)
        return RoadProfile(f"{base}{DATUM_SEP}{datum:.3f}", self.lanes, datum)


MIRROR_SUFFIX = "_mirrored"
"""Marks a profile as another one seen from the far end. See `mirrored`."""

DATUM_SEP = "@d"
"""Marks a profile as shifted by a specific datum. See `with_datum`."""


def mirror_name(name: str) -> str:
    """The name of `name`'s mirror. An involution, so applying it twice returns."""
    if name.endswith(MIRROR_SUFFIX):
        return name[: -len(MIRROR_SUFFIX)]
    return name + MIRROR_SUFFIX


def datum_base_name(name: str) -> str:
    """`name` with any existing datum suffix stripped, so `with_datum` never
    accumulates one - realigning an already-aligned road replaces its shift
    rather than adding to it."""
    if DATUM_SEP in name:
        return name.split(DATUM_SEP, 1)[0]
    return name
