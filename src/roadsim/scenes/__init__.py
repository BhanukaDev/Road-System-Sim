"""Scene registry. One entry per mode the app can start in.

`game` is the app: one world with runtime-switchable modes over it. `editor` is
M2's road-only shell, kept because it is the surface the M2 tests drive; `network`
and `debug` are the geometry scenes, and both stay reachable for geometry work.
"""

from __future__ import annotations

from .base import Scene
from .debug_geometry import DebugGeometryScene
from .editor import EditorScene
from .game import GameScene
from .network_demo import NetworkDemoScene

SCENES: dict[str, type[Scene]] = {
    GameScene.name: GameScene,
    EditorScene.name: EditorScene,
    NetworkDemoScene.name: NetworkDemoScene,
    DebugGeometryScene.name: DebugGeometryScene,
}

DEFAULT_SCENE = GameScene.name

__all__ = ["DEFAULT_SCENE", "SCENES", "Scene"]
