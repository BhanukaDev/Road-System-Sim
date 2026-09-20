"""Save files.

The assertion that matters is byte-identity across a round trip. A field that
quietly stops being written still *loads* into something plausible - only
comparing the text catches it.
"""

from __future__ import annotations

import json

import pytest

from roadsim.geometry import Vec2
from roadsim.road.network import RoadNetwork
from roadsim.road.presets import ASYMMETRIC_BOULEVARD, RAIL_DOUBLE, TRAM_AVENUE
from roadsim.scenes.network_demo import build_demo_network
from roadsim.serialization import SchemaError, dumps, load, loads, network_to_dict, save

from .conftest import approx, assert_vec


def test_round_trip_is_byte_identical():
    original = dumps(build_demo_network())
    assert dumps(loads(original)) == original


def test_round_trip_preserves_topology_and_geometry():
    before = build_demo_network()
    after = loads(dumps(before))

    assert set(after.nodes) == set(before.nodes)
    assert set(after.segments) == set(before.segments)
    for sid, segment in before.segments.items():
        twin = after.segments[sid]
        assert (twin.node_a, twin.node_b) == (segment.node_a, segment.node_b)
        assert twin.profile == segment.profile
        assert approx(twin.corner_radius, segment.corner_radius)
        assert approx(twin.path.length, segment.path.length)
        for a, b in zip(twin.control_points, segment.control_points):
            assert_vec(a, b)


def test_derived_state_is_not_stored_but_is_rebuilt():
    """Junctions and trims are derived (D5). They must not appear in the file,
    and they must be back after a load."""
    net = build_demo_network()
    payload = network_to_dict(net)
    text = json.dumps(payload)
    for word in ("trim", "junction", "path", "pieces"):
        assert word not in text

    loaded = loads(dumps(net))
    assert len(loaded.junctions) == len(net.junctions)
    for sid, segment in net.segments.items():
        assert approx(loaded.segments[sid].trim_a, segment.trim_a, 1e-6)
        assert approx(loaded.segments[sid].trim_b, segment.trim_b, 1e-6)


def test_only_the_profiles_in_use_are_written():
    net = RoadNetwork()
    net.connect(Vec2(-40.0, 0.0), Vec2(40.0, 0.0), TRAM_AVENUE)
    net.rebuild_all()
    assert set(network_to_dict(net)["profiles"]) == {TRAM_AVENUE.name}


def test_a_profile_survives_with_every_lane_intact():
    net = RoadNetwork()
    net.connect(Vec2(-40.0, 0.0), Vec2(40.0, 0.0), ASYMMETRIC_BOULEVARD)
    net.connect(Vec2(-40.0, 60.0), Vec2(40.0, 60.0), RAIL_DOUBLE)
    net.rebuild_all()

    loaded = loads(dumps(net))
    for segment in loaded.segments.values():
        original = net.segments[segment.id].profile
        assert segment.profile.lanes == original.lanes
        assert approx(segment.profile.datum, original.datum)


def test_an_empty_network_round_trips():
    assert dumps(loads(dumps(RoadNetwork()))) == dumps(RoadNetwork())


def test_saving_to_disk_round_trips(tmp_path):
    net = build_demo_network()
    path = save(net, tmp_path / "net.roadnet.json")
    assert dumps(load(path)) == dumps(net)


def test_an_unknown_version_is_rejected_clearly():
    payload = json.loads(dumps(build_demo_network()))
    payload["version"] = 99
    with pytest.raises(SchemaError, match="version"):
        loads(json.dumps(payload))


def test_a_missing_section_is_rejected_clearly():
    payload = json.loads(dumps(build_demo_network()))
    del payload["nodes"]
    with pytest.raises(SchemaError, match="nodes"):
        loads(json.dumps(payload))


def test_a_segment_naming_an_undeclared_profile_is_rejected():
    payload = json.loads(dumps(build_demo_network()))
    payload["segments"][0]["profile"] = "not_a_profile"
    with pytest.raises(SchemaError, match="not_a_profile"):
        loads(json.dumps(payload))


def test_an_unknown_lane_type_is_rejected():
    payload = json.loads(dumps(build_demo_network()))
    name = next(iter(payload["profiles"]))
    payload["profiles"][name]["lanes"][0]["type"] = "hovercraft"
    with pytest.raises(SchemaError):
        loads(json.dumps(payload))


def test_garbage_is_rejected_rather_than_crashing():
    with pytest.raises(SchemaError):
        loads("{ not json")
    with pytest.raises(SchemaError):
        loads("[1, 2, 3]")
