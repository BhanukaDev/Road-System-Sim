"""A point where segments meet. Owns nothing but its position and its id."""

from __future__ import annotations

from dataclasses import dataclass, field

from ..geometry import Vec2


@dataclass
class RoadNode:
    id: int
    position: Vec2
    segments: set[int] = field(default_factory=set)
    """Ids of the segments ending here. Maintained by `RoadNetwork`."""

    @property
    def degree(self) -> int:
        return len(self.segments)

    @property
    def is_dead_end(self) -> bool:
        return self.degree <= 1
