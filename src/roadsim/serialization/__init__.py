"""Saving and loading networks. Knows `road`, and nothing above it."""

from .io import dumps, load, loads, save
from .schema import SchemaError, network_from_dict, network_to_dict

__all__ = [
    "SchemaError",
    "dumps",
    "load",
    "loads",
    "network_from_dict",
    "network_to_dict",
    "save",
]
