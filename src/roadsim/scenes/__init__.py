"""Scene registry. One entry per mode the app can start in."""

from __future__ import annotations

from .base import Scene
from .debug_geometry import DebugGeometryScene
from .editor import EditorScene
from .network_demo import NetworkDemoScene

SCENES: dict[str, type[Scene]] = {
    EditorScene.name: EditorScene,
    NetworkDemoScene.name: NetworkDemoScene,
    DebugGeometryScene.name: DebugGeometryScene,
}

DEFAULT_SCENE = EditorScene.name

__all__ = ["DEFAULT_SCENE", "SCENES", "Scene"]
