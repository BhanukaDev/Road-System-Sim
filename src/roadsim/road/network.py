"""The road graph: nodes, segments, and the junctions derived from them.

The network owns ids and adjacency and nothing else. Junctions and trims are
rebuilt from dirty nodes (D5) - so any mutation only has to say *which nodes it
touched*, not remember what depends on them.

Mutators here are deliberately blunt and side-effect-free beyond the model. In
the rest of M2 they are driven by `Command` objects (D6), which is why each one
is a single named operation rather than a setter.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from itertools import count

from ..geometry import Vec2
from .junction import Junction, build_junction
from .node import RoadNode
from .profile import RoadProfile
from .segment import RoadSegment

SNAP_EPS = 1e-6


@dataclass
class RoadNetwork:
    nodes: dict[int, RoadNode] = field(default_factory=dict)
    segments: dict[int, RoadSegment] = field(default_factory=dict)
    junctions: dict[int, Junction] = field(default_factory=dict)
    """Keyed by node id. Derived - never saved, never trusted across a rebuild."""

    _node_ids: count = field(default_factory=lambda: count(1), repr=False)
    _segment_ids: count = field(default_factory=lambda: count(1), repr=False)
    _dirty: set[int] = field(default_factory=set, repr=False)

    # -- mutation ----------------------------------------------------------

    def add_node(self, position: Vec2, node_id: int | None = None) -> RoadNode:
        node_id = self._claim(self._node_ids, self.nodes, node_id)
        node = RoadNode(node_id, position)
        self.nodes[node_id] = node
        self._dirty.add(node_id)
        return node

    def add_segment(
        self,
        node_a: int,
        node_b: int,
        control_points: list[Vec2],
        profile: RoadProfile,
        corner_radius: float | None = None,
        segment_id: int | None = None,
    ) -> RoadSegment:
        """Add a segment between two existing nodes.

        The control points are snapped onto the nodes, because the nodes - not
        the stroke the user drew - decide where a road ends.
        """
        for nid in (node_a, node_b):
            if nid not in self.nodes:
                raise KeyError(f"no node {nid}")
        points = list(control_points)
        points[0] = self.nodes[node_a].position
        points[-1] = self.nodes[node_b].position

        segment_id = self._claim(self._segment_ids, self.segments, segment_id)
        kwargs = {} if corner_radius is None else {"corner_radius": corner_radius}
        segment = RoadSegment(segment_id, node_a, node_b, points, profile, **kwargs)
        self.segments[segment_id] = segment
        self.nodes[node_a].segments.add(segment_id)
        self.nodes[node_b].segments.add(segment_id)
        self._dirty.update((node_a, node_b))
        return segment

    def connect(
        self,
        a: Vec2,
        b: Vec2,
        profile: RoadProfile,
        via: list[Vec2] | None = None,
        corner_radius: float | None = None,
    ) -> RoadSegment:
        """Convenience: reuse or create the end nodes, then add the segment."""
        node_a = self.node_at(a) or self.add_node(a)
        node_b = self.node_at(b) or self.add_node(b)
        points = [node_a.position, *(via or []), node_b.position]
        return self.add_segment(node_a.id, node_b.id, points, profile, corner_radius)

    def remove_segment(self, segment_id: int) -> None:
        segment = self.segments.pop(segment_id)
        for nid in (segment.node_a, segment.node_b):
            self.nodes[nid].segments.discard(segment_id)
            self._dirty.add(nid)

    def remove_node(self, node_id: int) -> None:
        for segment_id in list(self.nodes[node_id].segments):
            self.remove_segment(segment_id)
        del self.nodes[node_id]
        self.junctions.pop(node_id, None)
        self._dirty.discard(node_id)

    def move_node(self, node_id: int, position: Vec2) -> None:
        node = self.nodes[node_id]
        node.position = position
        for segment_id in node.segments:
            segment = self.segments[segment_id]
            for at_a in (True, False):
                if (segment.node_a if at_a else segment.node_b) == node_id:
                    segment.set_endpoint(at_a, position)
            self._touch_ends(segment)

    def set_profile(self, segment_id: int, profile: RoadProfile) -> None:
        segment = self.segments[segment_id]
        segment.profile = profile
        self._touch_ends(segment)

    def split_segment(self, segment_id: int, s: float) -> tuple[int, int, int]:
        """Insert a node at arc length `s` and replace the segment with two.

        This is what a T-junction *is* when you draw onto an existing road.
        Both halves are refitted from their own corner points, so the shape
        shifts slightly at the split - the original fillets are not preserved,
        and preserving them is not worth the complexity (M2 design).

        Returns `(first segment id, second segment id, new node id)`.
        """
        old = self.segments[segment_id]
        if not 0.0 < s < old.path.length:
            raise ValueError(f"cannot split segment {segment_id} at s={s}")

        cut = old.path.sample(s).position
        head, tail = old.control_points[0], old.control_points[-1]
        before = [head, *_corner_points(old, 0.0, s), cut]
        after = [cut, *_corner_points(old, s, old.path.length), tail]
        node_a, node_b, profile, radius = (
            old.node_a,
            old.node_b,
            old.profile,
            old.corner_radius,
        )

        mid = self.add_node(cut)
        self.remove_segment(segment_id)
        first = self.add_segment(node_a, mid.id, before, profile, radius)
        second = self.add_segment(mid.id, node_b, after, profile, radius)
        return first.id, second.id, mid.id

    # -- queries -----------------------------------------------------------

    def node_at(self, position: Vec2, radius: float = SNAP_EPS) -> RoadNode | None:
        best, best_d = None, radius
        for node in self.nodes.values():
            d = node.position.distance_to(position)
            if d <= best_d:
                best, best_d = node, d
        return best

    def segments_at(self, node_id: int) -> list[tuple[RoadSegment, bool]]:
        """Every `(segment, at_a)` end meeting at a node. A loop counts twice."""
        ends: list[tuple[RoadSegment, bool]] = []
        for segment_id in sorted(self.nodes[node_id].segments):
            segment = self.segments[segment_id]
            if segment.node_a == node_id:
                ends.append((segment, True))
            if segment.node_b == node_id:
                ends.append((segment, False))
        return ends

    # -- rebuild -----------------------------------------------------------

    @property
    def dirty_nodes(self) -> frozenset[int]:
        return frozenset(self._dirty)

    def mark_dirty(self, node_id: int) -> None:
        self._dirty.add(node_id)

    def rebuild_dirty(self) -> None:
        """Recompute junctions for dirty nodes, then retrim every segment they
        touch. Call once per frame after commands land - never mid-command."""
        dirty, self._dirty = self._dirty, set()
        touched: set[int] = set()
        for node_id in dirty:
            if node_id not in self.nodes:
                self.junctions.pop(node_id, None)
                continue
            ends = self.segments_at(node_id)
            junction = build_junction(node_id, self.nodes[node_id].position, ends)
            if junction is None:
                self.junctions.pop(node_id, None)
            else:
                self.junctions[node_id] = junction
            touched.update(segment.id for segment, _ in ends)
        for segment_id in touched:
            self._retrim(self.segments[segment_id])

    def rebuild_all(self) -> None:
        self._dirty.update(self.nodes)
        self.rebuild_dirty()

    def _retrim(self, segment: RoadSegment) -> None:
        segment.trim_a = self._trim_at(segment, True)
        segment.trim_b = self._trim_at(segment, False)

    def _trim_at(self, segment: RoadSegment, at_a: bool) -> float:
        node_id = segment.node_a if at_a else segment.node_b
        junction = self.junctions.get(node_id)
        return 0.0 if junction is None else junction.trim_for(segment.id, at_a)

    def _touch_ends(self, segment: RoadSegment) -> None:
        self._dirty.update((segment.node_a, segment.node_b))

    @staticmethod
    def _claim(ids: count, store: dict, wanted: int | None) -> int:
        if wanted is None:
            while (candidate := next(ids)) in store:
                pass
            return candidate
        if wanted in store:
            raise KeyError(f"id {wanted} already taken")
        return wanted


def _corner_points(segment: RoadSegment, s0: float, s1: float) -> list[Vec2]:
    """The original control points falling strictly inside an arc-length span.

    Control points are not on the fitted path - a filleted corner cuts inside
    them - so each is placed by projecting it back onto the path.
    """
    path = segment.path
    return [
        p
        for p in segment.control_points[1:-1]
        if s0 + SNAP_EPS < path.project(p) < s1 - SNAP_EPS
    ]
