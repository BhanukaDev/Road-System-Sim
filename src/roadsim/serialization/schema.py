"""Versioned dict <-> model conversion.

Only **authoritative** state is written: node positions, segment control points,
corner radii, corner-handle pulls and profiles. Paths, trims and junctions are
derived (D5) and are rebuilt on load - persisting them is how a save file ends
up disagreeing with itself.

A `pull_a`/`pull_b` key is written only when it is set - `None` is the common
case, and a file full of null pulls would bury the segments that actually have
one.

Ordering is deterministic everywhere (ids ascending, profiles by name) so that
save -> load -> save is byte-identical. That round trip is the test that catches
a field quietly going missing.
"""

from __future__ import annotations

from typing import Any

from ..geometry import Vec2
from ..road.lane import Direction, LaneSpec, LaneType
from ..road.network import RoadNetwork
from ..road.profile import RoadProfile

VERSION = 2
"""Version 2 added the optional `profile_b` key on a segment - a lane-change
taper (D26). A version 1 file has none and loads unchanged."""
READABLE = (1, 2)


class SchemaError(ValueError):
    """The payload is not something this version of the model can load."""


# -- writing ---------------------------------------------------------------


def network_to_dict(network: RoadNetwork) -> dict[str, Any]:
    profiles = {seg.profile.name: seg.profile for seg in network.segments.values()}
    for seg in network.segments.values():
        if seg.profile_b is not None:
            profiles[seg.profile_b.name] = seg.profile_b
    return {
        "version": VERSION,
        "profiles": {
            name: profile_to_dict(profiles[name]) for name in sorted(profiles)
        },
        "nodes": [
            {"id": nid, "x": node.position.x, "y": node.position.y}
            for nid, node in sorted(network.nodes.items())
        ],
        "segments": [
            {
                "id": sid,
                "a": seg.node_a,
                "b": seg.node_b,
                "profile": seg.profile.name,
                "radius": seg.corner_radius,
                "points": [[p.x, p.y] for p in seg.control_points],
                **({"pull_a": seg.pull_a} if seg.pull_a is not None else {}),
                **({"pull_b": seg.pull_b} if seg.pull_b is not None else {}),
                **(
                    {"profile_b": seg.profile_b.name}
                    if seg.profile_b is not None
                    else {}
                ),
            }
            for sid, seg in sorted(network.segments.items())
        ],
    }


def profile_to_dict(profile: RoadProfile) -> dict[str, Any]:
    return {
        "datum": profile.datum,
        "lanes": [
            {
                "width": lane.width,
                "direction": lane.direction.value,
                "type": lane.type.value,
                "speed_limit": lane.speed_limit,
            }
            for lane in profile.lanes
        ],
    }


# -- reading ---------------------------------------------------------------


def network_from_dict(payload: dict[str, Any]) -> RoadNetwork:
    version = payload.get("version")
    if version not in READABLE:
        raise SchemaError(
            f"unsupported save version {version!r}; this build reads versions {READABLE}"
        )

    profiles = {
        name: profile_from_dict(name, data)
        for name, data in _require(payload, "profiles").items()
    }

    network = RoadNetwork()
    for node in _require(payload, "nodes"):
        network.add_node(Vec2(float(node["x"]), float(node["y"])), node_id=node["id"])
    for seg in _require(payload, "segments"):
        name = seg["profile"]
        if name not in profiles:
            raise SchemaError(f"segment {seg['id']} uses undeclared profile {name!r}")
        name_b = seg.get("profile_b")
        if name_b is not None and name_b not in profiles:
            raise SchemaError(
                f"segment {seg['id']} tapers to undeclared profile {name_b!r}"
            )
        added = network.add_segment(
            seg["a"],
            seg["b"],
            [Vec2(float(x), float(y)) for x, y in seg["points"]],
            profiles[name],
            corner_radius=float(seg["radius"]),
            segment_id=seg["id"],
            profile_b=None if name_b is None else profiles[name_b],
        )
        if "pull_a" in seg:
            added.pull_a = float(seg["pull_a"])
        if "pull_b" in seg:
            added.pull_b = float(seg["pull_b"])
    network.rebuild_all()
    return network


def profile_from_dict(name: str, data: dict[str, Any]) -> RoadProfile:
    try:
        lanes = tuple(
            LaneSpec(
                float(lane["width"]),
                Direction(lane["direction"]),
                LaneType(lane["type"]),
                lane.get("speed_limit"),
            )
            for lane in data["lanes"]
        )
    except (KeyError, TypeError) as exc:
        raise SchemaError(f"profile {name!r} is malformed: {exc}") from exc
    except ValueError as exc:
        raise SchemaError(f"profile {name!r} has an unknown lane value: {exc}") from exc
    return RoadProfile(name, lanes, float(data.get("datum", 0.0)))


def _require(payload: dict[str, Any], key: str):
    if key not in payload:
        raise SchemaError(f"save file has no {key!r}")
    return payload[key]
