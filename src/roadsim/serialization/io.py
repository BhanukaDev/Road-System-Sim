"""JSON on disk. Thin on purpose - `schema.py` decides what a network *is*."""

from __future__ import annotations

import json
from pathlib import Path

from ..road.network import RoadNetwork
from .schema import SchemaError, network_from_dict, network_to_dict

INDENT = 2
SUFFIX = ".roadnet.json"


def dumps(network: RoadNetwork) -> str:
    """Deterministic text. Two saves of one network compare byte for byte."""
    return json.dumps(network_to_dict(network), indent=INDENT) + "\n"


def loads(text: str) -> RoadNetwork:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise SchemaError(f"not valid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise SchemaError("save file must be a JSON object")
    return network_from_dict(payload)


def save(network: RoadNetwork, path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dumps(network), encoding="utf-8")
    return path


def load(path: str | Path) -> RoadNetwork:
    return loads(Path(path).read_text(encoding="utf-8"))
