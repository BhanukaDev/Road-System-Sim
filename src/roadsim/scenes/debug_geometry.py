"""M1 verification surface for the geometry kernel.

There is no test suite, so this scene *is* the test. It draws the things that go
wrong when arc/line fitting or offsetting is subtly broken:

* offset ribbons that should stay exactly parallel through arc <-> line joins
* normal hairs, which fan out or cross if the frame is wrong
* stations at fixed arc lengths, which bunch up if `s` drifts
* arc centres and radii, which expose a tangency failure instantly

Draw your own test paths: click to place corners, drag to sketch freehand.
"""

from __future__ import annotations

import pygame

from .. import config
from ..geometry import Path, Vec2, fit_freehand, fit_polyline
from ..render import curves
from ..render.camera import Camera
from .base import Scene

DEMO_POINTS = [
    Vec2(-90.0, -30.0),
    Vec2(-40.0, -30.0),
    Vec2(-10.0, 20.0),
    Vec2(30.0, 25.0),
    Vec2(45.0, -20.0),
    Vec2(95.0, -25.0),
]

LANE_EDGES = (-8.0, -4.5, -1.5, 1.5, 5.0)
"""Asymmetric on purpose: two lanes left of centre, one narrow one right.
If the kernel is right these stay parallel at every radius and zoom."""

RADII = (4.0, 12.0, 25.0, 45.0)


class DebugGeometryScene(Scene):
    name = "debug"

    def __init__(self, camera: Camera) -> None:
        super().__init__(camera)
        self.radius_index = 1
        self.corner_points: list[Vec2] = list(DEMO_POINTS)
        self.freehand: list[Vec2] | None = None
        self.sketching = False
        self.show_normals = True
        self.show_stations = True
        self.show_centers = True
        self.show_lanes = True
        self.cursor_world = Vec2(0.0, 0.0)
        self._press_pos = (0, 0)
        self.error: str | None = None
        self._path: Path | None = None
        self._rebuild()

    # -- model ------------------------------------------------------------

    @property
    def radius(self) -> float:
        return RADII[self.radius_index]

    def _rebuild(self) -> None:
        self.error = None
        try:
            if self.freehand is not None and len(self.freehand) >= 2:
                self._path = fit_freehand(self.freehand, self.radius, tolerance=2.0)
            elif len(self.corner_points) >= 2:
                self._path = fit_polyline(self.corner_points, self.radius)
            else:
                self._path = None
        except (ValueError, ZeroDivisionError) as exc:
            self._path = None
            self.error = str(exc)

    # -- input ------------------------------------------------------------

    def handle_event(self, event: pygame.event.Event) -> bool:
        if event.type == pygame.MOUSEMOTION:
            self.cursor_world = self.camera.to_world(*event.pos)
            if self.sketching and self.freehand is not None:
                self.freehand.append(self.cursor_world)
                self._rebuild()
            return False

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            self.sketching = True
            self.freehand = None
            self._press_pos = event.pos
            return True

        if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            self.sketching = False
            if self.freehand is None:  # a click, not a drag
                self.corner_points.append(self.camera.to_world(*event.pos))
                self._rebuild()
            return True

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 3:
            self._reset()
            return True

        if event.type == pygame.KEYDOWN:
            return self._handle_key(event.key)
        return False

    def _handle_key(self, key: int) -> bool:
        if key == pygame.K_n:
            self.show_normals = not self.show_normals
        elif key == pygame.K_s:
            self.show_stations = not self.show_stations
        elif key == pygame.K_c:
            self.show_centers = not self.show_centers
        elif key == pygame.K_l:
            self.show_lanes = not self.show_lanes
        elif key == pygame.K_r:
            self.radius_index = (self.radius_index + 1) % len(RADII)
            self._rebuild()
        elif key == pygame.K_BACKSPACE:
            self._reset()
        else:
            return False
        return True

    def _reset(self) -> None:
        self.corner_points = list(DEMO_POINTS)
        self.freehand = None
        self._rebuild()

    def update(self, dt: float) -> None:
        # Promote a held left button into a freehand stroke once it has moved.
        if self.sketching and self.freehand is None:
            press = self.camera.to_world(*self._press_pos)
            if press.distance_to(self.cursor_world) * self.camera.zoom > 6.0:
                self.freehand = [press, self.cursor_world]
                self._rebuild()

    # -- drawing ----------------------------------------------------------

    def draw(self, surface: pygame.Surface) -> None:
        path = self._path
        if path is None:
            return
        cam = self.camera

        if self.show_lanes:
            for left, right in zip(LANE_EDGES, LANE_EDGES[1:]):
                curves.draw_path_ribbon(surface, cam, path, left, right)

        if self.show_centers:
            curves.draw_arc_centers(surface, cam, path)
        if self.show_normals:
            curves.draw_normals(surface, cam, path)

        curves.draw_path(surface, cam, path)

        if self.show_stations:
            curves.draw_stations(surface, cam, path)

        self._draw_corner_points(surface)
        self._draw_projection(surface, path)

    def _draw_corner_points(self, surface: pygame.Surface) -> None:
        if self.freehand is not None:
            return
        for p in self.corner_points:
            pygame.draw.circle(surface, (120, 128, 140), self.camera.to_screen(p), 3, 1)

    def _draw_projection(self, surface: pygame.Surface, path: Path) -> None:
        """Nearest point on the path to the cursor - exercises Path.project."""
        frame = path.sample(path.project(self.cursor_world))
        pygame.draw.line(
            surface,
            (80, 200, 150),
            self.camera.to_screen(self.cursor_world),
            self.camera.to_screen(frame.position),
            1,
        )
        pygame.draw.circle(surface, (80, 200, 150), self.camera.to_screen(frame.position), 4, 1)

    def hud_lines(self) -> list[str]:
        path = self._path
        lines = [f"scene: {self.name}   fillet radius: {self.radius:.0f} m  [R]"]
        if self.error:
            lines.append(f"# fit failed: {self.error}")
        if path is not None:
            kinds = ", ".join(type(p).__name__.replace("Segment", "") for p in path.pieces)
            lines.append(f"length {path.length:7.2f} m   {len(path.pieces)} pieces: {kinds}")
            s = path.project(self.cursor_world)
            lines.append(f"cursor -> s {s:7.2f} m   curvature {path.sample(s).curvature:+.4f}")
        lines.append("# click: add corner   drag: freehand   right-click: reset")
        lines.append("# [N]ormals [S]tations arc [C]enters [L]anes")
        return lines
