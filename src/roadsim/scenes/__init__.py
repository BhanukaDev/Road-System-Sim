"""Scene registry. One entry per mode the app can start in."""

from __future__ import annotations

from .base import Scene
from .debug_geometry import DebugGeometryScene

SCENES: dict[str, type[Scene]] = {
    DebugGeometryScene.name: DebugGeometryScene,
}

DEFAULT_SCENE = DebugGeometryScene.name

__all__ = ["DEFAULT_SCENE", "SCENES", "Scene"]
