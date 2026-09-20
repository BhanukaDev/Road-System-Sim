"""World <-> screen transform. The single place where y is flipped.

World space is metres, +y up. Screen space is pixels, +y down.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .. import config
from ..geometry import Vec2


@dataclass
class Camera:
    center: Vec2 = field(default_factory=lambda: Vec2(0.0, 0.0))
    """World point shown at the middle of the viewport."""
    zoom: float = config.DEFAULT_ZOOM
    """Pixels per metre."""
    viewport: tuple[int, int] = config.WINDOW_SIZE

    def to_screen(self, p: Vec2) -> tuple[float, float]:
        w, h = self.viewport
        return (
            (p.x - self.center.x) * self.zoom + w * 0.5,
            h * 0.5 - (p.y - self.center.y) * self.zoom,
        )

    def to_screen_xy(self, x: float, y: float) -> tuple[float, float]:
        w, h = self.viewport
        return (
            (x - self.center.x) * self.zoom + w * 0.5,
            h * 0.5 - (y - self.center.y) * self.zoom,
        )

    def to_world(self, sx: float, sy: float) -> Vec2:
        w, h = self.viewport
        return Vec2(
            (sx - w * 0.5) / self.zoom + self.center.x,
            (h * 0.5 - sy) / self.zoom + self.center.y,
        )

    def pan_pixels(self, dx: float, dy: float) -> None:
        self.center = Vec2(
            self.center.x - dx / self.zoom, self.center.y + dy / self.zoom
        )

    def zoom_at(self, factor: float, sx: float, sy: float) -> None:
        """Zoom keeping the world point under the cursor pinned to the cursor."""
        anchor = self.to_world(sx, sy)
        self.zoom = min(max(self.zoom * factor, config.MIN_ZOOM), config.MAX_ZOOM)
        moved = self.to_world(sx, sy)
        self.center = self.center + (anchor - moved)

    @property
    def world_tolerance(self) -> float:
        """Flatten tolerance in metres that yields a constant screen-space error.

        This is why curves stay smooth when you zoom in instead of turning into
        visible polygons.
        """
        return config.FLATTEN_TOLERANCE_PX / self.zoom

    def world_bounds(self) -> tuple[Vec2, Vec2]:
        w, h = self.viewport
        return self.to_world(0, h), self.to_world(w, 0)
