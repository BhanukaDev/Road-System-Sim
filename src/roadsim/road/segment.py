"""A stretch of road between two nodes.

`control_points` is the source of truth; `path` is *derived* from it by
`fit_polyline`. That split is what makes moving a node, changing the corner
radius and saving to disk all one-liners: they touch control points and refit.

`trim_a` / `trim_b` are how much each end gives up to a junction. They are
derived too - recomputed by `RoadNetwork.rebuild_dirty` - and never stored (D5).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .. import config
from ..geometry import Path, Ribbon, Sample, Vec2, build_ribbon, fit_polyline
from .profile import RoadProfile


@dataclass
class RoadSegment:
    id: int
    node_a: int
    node_b: int
    control_points: list[Vec2]
    """AUTHORITATIVE. [0] sits on node_a, [-1] on node_b."""
    profile: RoadProfile
    corner_radius: float = config.DEFAULT_CORNER_RADIUS
    trim_a: float = 0.0
    trim_b: float = 0.0
    path: Path = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self.refit()

    # -- authoritative state ----------------------------------------------

    def refit(self) -> None:
        """Rebuild the fitted path from the control points. Cheap; call freely."""
        self.path = fit_polyline(self.control_points, self.corner_radius)

    def set_endpoint(self, at_a: bool, position: Vec2) -> None:
        self.control_points[0 if at_a else -1] = position
        self.refit()

    def other_node(self, node_id: int) -> int:
        if node_id == self.node_a:
            return self.node_b
        if node_id == self.node_b:
            return self.node_a
        raise KeyError(f"segment {self.id} does not touch node {node_id}")

    def ends_at(self, node_id: int) -> bool:
        return node_id in (self.node_a, self.node_b)

    def is_at_a(self, node_id: int) -> bool:
        """True when `node_id` is this segment's A end.

        A segment whose two ends are the same node (a loop) answers A first;
        callers that care about both ends iterate `(True, False)` instead.
        """
        if node_id == self.node_a:
            return True
        if node_id == self.node_b:
            return False
        raise KeyError(f"segment {self.id} does not touch node {node_id}")

    # -- derived geometry --------------------------------------------------

    @property
    def length(self) -> float:
        return self.path.length

    @property
    def carriageway_length(self) -> float:
        return self.path.length - self.trim_a - self.trim_b

    @property
    def is_too_short(self) -> bool:
        """The junctions at both ends have eaten the road between them.

        The user hits this within a minute of drawing, so it is a flag the
        renderer checks - never an exception out of `Path.trimmed` mid-frame.
        """
        return self.carriageway_length < config.MIN_CARRIAGEWAY

    def end_s(self, at_a: bool) -> float:
        """Arc length of the carriageway end at this side of the segment."""
        return self.trim_a if at_a else self.path.length - self.trim_b

    def end_frame(self, at_a: bool) -> Sample:
        """Frame where the carriageway meets the junction. Tangent stays A -> B."""
        return self.path.sample(self.end_s(at_a))

    def outgoing_dir(self, at_a: bool) -> Vec2:
        """Unit direction leaving the node at that end, pointing *away* from it."""
        tangent = self.path.sample(0.0 if at_a else self.path.length).tangent
        return tangent if at_a else -tangent

    @property
    def carriageway_path(self) -> Path:
        """The path with both junction bites taken out of it."""
        if self.is_too_short:
            raise ValueError(f"segment {self.id} is too short to have a carriageway")
        return self.path.shortened(self.trim_a, self.trim_b)

    def lane_ribbon(self, k: int, tolerance: float) -> Ribbon:
        """Lane `k` as a ribbon, exact to `profile.lane_bounds(k)`.

        Built by offsetting, never by resampling the centreline - so a lane edge
        stays exactly its offset from the centreline at any zoom.
        """
        left, right = self.profile.lane_bounds(k)
        return build_ribbon(
            self.path,
            left,
            right,
            tolerance,
            s0=self.trim_a,
            s1=self.path.length - self.trim_b,
        )

    def lane_centerline(self, k: int) -> Path:
        """Lane `k`'s centre, as an exact offset path. M4 will follow these."""
        return self.path.offset(self.profile.lane_center(k))
