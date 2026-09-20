"""Derived traffic lanes: one path per drivable lane, per travel direction."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from .lane import Direction, LaneSpec


@dataclass(frozen=True, slots=True)
class LanePath:
    segment_id: int
    lane_index: int
    direction: Direction
    start_node: int
    end_node: int


@dataclass(frozen=True, slots=True)
class LaneGraph:
    _by_segment: dict[int, tuple[LanePath, ...]] = field(default_factory=dict)
    _by_node: dict[int, tuple[LanePath, ...]] = field(default_factory=dict)

    def paths_for_segment(self, segment_id: int) -> tuple[LanePath, ...]:
        return self._by_segment.get(segment_id, ())

    def paths_for_node(self, node_id: int) -> tuple[LanePath, ...]:
        return self._by_node.get(node_id, ())

    @property
    def paths(self) -> tuple[LanePath, ...]:
        out: list[LanePath] = []
        for paths in self._by_segment.values():
            out.extend(paths)
        return tuple(out)


def build_lane_graph(segments: list[tuple[int, int, tuple[LaneSpec, ...]]]) -> LaneGraph:
    """Build one travel path for every drivable lane on each segment.

    A lane marked `Direction.BOTH` contributes both directions, while a lane that
    does not carry vehicles is ignored.
    """
    by_segment: dict[int, list[LanePath]] = defaultdict(list)
    by_node: dict[int, list[LanePath]] = defaultdict(list)

    for segment_id, node_a, node_b, profile_lanes in segments:
        for lane_index, lane in enumerate(profile_lanes):
            if not lane.type.carries_vehicles:
                continue

            road_dirs = _lane_directions(lane.direction)
            for direction in road_dirs:
                start, end = _start_end(segment_id, node_a, node_b, direction)
                path = LanePath(segment_id, lane_index, direction, start, end)
                by_segment[segment_id].append(path)
                by_node[start].append(path)
                by_node[end].append(path)

    return LaneGraph(
        _by_segment={k: tuple(v) for k, v in by_segment.items()},
        _by_node={k: tuple(v) for k, v in by_node.items()},
    )


def _lane_directions(direction: Direction) -> tuple[Direction, ...]:
    if direction is Direction.FORWARD:
        return (Direction.FORWARD,)
    if direction is Direction.BACKWARD:
        return (Direction.BACKWARD,)
    if direction is Direction.BOTH:
        return (Direction.FORWARD, Direction.BACKWARD)
    return ()


def _start_end(segment_id: int, node_a: int, node_b: int, direction: Direction) -> tuple[int, int]:
    if direction is Direction.FORWARD:
        return node_a, node_b
    if direction is Direction.BACKWARD:
        return node_b, node_a
    raise ValueError(f"segment {segment_id} lane direction must be traffic, not {direction!r}")
