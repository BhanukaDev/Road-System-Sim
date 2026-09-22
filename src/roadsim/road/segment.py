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
from ..geometry import (
    ArcSegment,
    LineSegment,
    Path,
    Ribbon,
    Sample,
    Vec2,
    build_ribbon,
    fit_polyline,
)
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
    pull_a: float | None = None
    """Corner-handle override for how far this end pulls back at a junction.
    `None` means derive it from the real kerb geometry, like `trim_a` itself."""
    pull_b: float | None = None
    profile_b: RoadProfile | None = None
    """Set on a *lane-change taper* (D26): the cross-section at the B end,
    with `profile` then being the one at the A end and the lane edges running
    straight between the two. `None` - the ordinary road - means the section is
    `profile` from end to end.

    A taper is always straight: exactly two control points, so its edges are
    line segments between the two mouths and stay exact (D1). It is the stored
    answer to "how long does the width change take", where a two-arm junction
    of differing profiles is the derived one for a node nobody drew a taper at.
    """
    heading_a: Vec2 | None = field(default=None, repr=False)
    heading_b: Vec2 | None = field(default=None, repr=False)
    """DERIVED, tapers only: the direction each mouth faces, in the A -> B
    sense, read off the road either side at rebuild (`RoadNetwork.
    _refresh_headings`). A taper's two mouths need not be in line - the road
    beyond it is centred on its own body, which the arrangement put to one
    side of the road before it (D28) - so its chord is skewed a few degrees
    from both roads, while each mouth still has to face its own road exactly
    for the joint there to be seamless. `None`, or a taper left dangling,
    falls back to the chord."""
    path: Path = field(init=False, repr=False)

    def __post_init__(self) -> None:
        if self.profile_b is not None and len(self.control_points) != 2:
            raise ValueError(
                f"segment {self.id} tapers between two profiles and must be a"
                f" straight of two control points, not {len(self.control_points)}"
            )
        self.refit()

    # -- cross-section -----------------------------------------------------

    @property
    def is_transition(self) -> bool:
        return self.profile_b is not None

    def profile_at(self, at_a: bool) -> RoadProfile:
        """The cross-section at one end - what a junction, cap or anchor at
        that end must read, since a taper has two."""
        if at_a or self.profile_b is None:
            return self.profile
        return self.profile_b

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

    def pull_at(self, at_a: bool) -> float | None:
        return self.pull_a if at_a else self.pull_b

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

    @property
    def is_degenerate(self) -> bool:
        """True when a curve here is too tight for this profile's own width.

        An edge `d` inside an arc of radius `r` has radius `r - d`. Once `d`
        reaches `r` that edge folds through the arc centre: the exact route
        (`lane_centerline`, and every collision query built on `path.offset`)
        raises `DegenerateOffsetError`, and the sampled route (`lane_ribbon`)
        quietly renders the lane inside out - a self-crossing outline that draws
        as holes and bowties, worst on the widest lanes, which is to say the
        pavements.

        So it is a flag the renderer checks, exactly like `is_too_short` - never
        an exception out of a ribbon mid-frame. `fit_polyline` clamps a fillet
        against its neighbouring straights but knows nothing about how wide the
        road is, so nothing upstream rules this out.
        """
        return self.tightest_clearance() < config.MIN_LANE_CLEARANCE

    def tightest_clearance(self) -> float:
        """Least radius left at any inner lane edge. `inf` when there is no arc.

        Which side is *inner* is the turn direction: a left turn (positive sweep)
        curves around a centre on its left, so the left extent is the one at risk
        (D3). Getting this backwards flags right-hand curves and passes left-hand
        ones, which looks like a rendering bug rather than a sign error.
        """
        worst = float("inf")
        for piece in self.path.pieces:
            if not isinstance(piece, ArcSegment):
                continue
            inner = (
                self.profile.extent_left
                if piece.turn_sign > 0.0
                else self.profile.extent_right
            )
            worst = min(worst, piece.radius - inner)
        return worst

    @property
    def is_broken(self) -> bool:
        """Either failure mode: eaten by its junctions, or curved too tight.

        One property so the renderer asks one question. Which one it is belongs
        in the HUD, where the user can act on it - not in the draw loop.
        """
        return self.is_too_short or self.is_degenerate

    def end_s(self, at_a: bool) -> float:
        """Arc length of the carriageway end at this side of the segment."""
        return self.trim_a if at_a else self.path.length - self.trim_b

    def end_frame(self, at_a: bool) -> Sample:
        """Frame where the carriageway meets the junction. Tangent stays A -> B."""
        return self.frame_at(self.end_s(at_a), at_a)

    def frame_at(self, s: float, at_a: bool) -> Sample:
        """The frame at station `s`, facing the way the `at_a` mouth faces.

        An ordinary road's frame is its path's. A taper's mouth faces the road
        beyond it (`heading_a` / `heading_b`), which its skewed chord does not,
        so its edges at either end are laid along that road's own normal and
        meet it flush.
        """
        sample = self.path.sample(s)
        heading = self.heading_a if at_a else self.heading_b
        if not self.is_transition or heading is None:
            return sample
        return Sample(sample.s, sample.position, heading, 0.0)

    def outgoing_dir(self, at_a: bool) -> Vec2:
        """Unit direction leaving the node at that end, pointing *away* from it."""
        tangent = self.frame_at(0.0 if at_a else self.path.length, at_a).tangent
        return tangent if at_a else -tangent

    def kerb_line(self, left: bool) -> LineSegment:
        """A taper's kerb: the straight from one mouth's edge to the other's.

        Not `path.offset(extent)` - the two mouths have different sections,
        and need not be in line, so a taper's kerb is not parallel to its chord
        and is not at a constant offset from anything. It is exactly the line
        between the two edge points, which is what the renderer fills and what
        a junction next door has to trim against.
        """
        frame_a = self.frame_at(0.0, True)
        frame_b = self.frame_at(self.path.length, False)
        index = 0 if left else -1
        start = frame_a.position + frame_a.normal * self.profile_at(True).edges[index]
        end = frame_b.position + frame_b.normal * self.profile_at(False).edges[index]
        return LineSegment(start, end)

    @property
    def carriageway_path(self) -> Path:
        """The path with both junction bites taken out of it."""
        if self.is_too_short:
            raise ValueError(f"segment {self.id} is too short to have a carriageway")
        return self.path.shortened(self.trim_a, self.trim_b)

    def lane_ribbon(
        self,
        k: int,
        tolerance: float,
        s0: float | None = None,
        s1: float | None = None,
    ) -> Ribbon:
        """Lane `k` as a ribbon, exact to `profile.lane_bounds(k)`.

        Built by offsetting, never by resampling the centreline - so a lane edge
        stays exactly its offset from the centreline at any zoom. Defaults to
        the carriageway span; `s0`/`s1` narrow that further, which is what a
        median taper needs to stop its constant-width ribbon short of the mouth
        (`road/median_taper.py`) without touching every other lane's call.
        """
        left, right = self.profile.lane_bounds(k)
        return build_ribbon(
            self.path,
            left,
            right,
            tolerance,
            s0=self.trim_a if s0 is None else s0,
            s1=(self.path.length - self.trim_b) if s1 is None else s1,
        )

    def lane_centerline(self, k: int) -> Path:
        """Lane `k`'s centre, as an exact offset path. M4 will follow these."""
        return self.path.offset(self.profile.lane_center(k))
