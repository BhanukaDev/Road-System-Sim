"""Window and main loop. Camera *control* lives in `render/camera_input.py`.

Event order, first consumer wins:

1. the window itself - quit, resize, HUD toggle
2. the scene, and through it the active tool
3. the app's own late keys - `Esc`, `Home`
4. the camera controller

The scene sits above the late keys deliberately. `Esc` means "abandon what I am
drawing" while a tool has something in progress and "quit" otherwise, and the
only way the tool gets to make that call is by being asked first.
"""

from __future__ import annotations

import pygame

from . import config
from .render.camera import Camera
from .render.camera_input import CameraController
from .render.grid import draw_grid
from .render.hud import Hud
from .scenes import DEFAULT_SCENE, SCENES, Scene


class App:
    def __init__(self, scene_name: str = DEFAULT_SCENE) -> None:
        pygame.init()
        pygame.display.set_caption(config.WINDOW_TITLE)
        self.surface = pygame.display.set_mode(config.WINDOW_SIZE, pygame.RESIZABLE)
        self.clock = pygame.time.Clock()
        self.hud = Hud()
        self.camera = Camera(viewport=self.surface.get_size())
        self.controller = CameraController(self.camera)
        self.scene: Scene = SCENES[scene_name](self.camera)
        self.show_hud = True
        self.running = False

    def run(self) -> None:
        self.running = True
        while self.running:
            dt = self.clock.tick(config.TARGET_FPS) / 1000.0
            self._pump_events()
            self.controller.update(
                dt,
                pygame.key.get_pressed(),
                pygame.mouse.get_pos() if pygame.mouse.get_focused() else None,
                self.surface.get_size(),
            )
            self.scene.update(dt)
            self._draw()
        pygame.quit()

    # -- events -----------------------------------------------------------

    def _pump_events(self) -> None:
        for event in pygame.event.get():
            if self._handle_window_event(event):
                continue
            if self.scene.handle_event(event):
                continue
            if self._handle_late_key(event):
                continue
            self.controller.handle_event(event)

    def _handle_window_event(self, event: pygame.event.Event) -> bool:
        """The window's own business. Nothing below gets a say in these."""
        if event.type == pygame.QUIT:
            self.running = False
            return True
        if event.type == pygame.VIDEORESIZE:
            self.camera.viewport = (event.w, event.h)
            return True
        if event.type == pygame.KEYDOWN and event.key == pygame.K_F1:
            self.show_hud = not self.show_hud
            return True
        return False

    def _handle_late_key(self, event: pygame.event.Event) -> bool:
        """Keys the scene declined. `Esc` only quits once no tool wants it."""
        if event.type != pygame.KEYDOWN:
            return False
        if event.key == pygame.K_ESCAPE:
            self.running = False
            return True
        if event.key == pygame.K_HOME:
            self.camera.center = type(self.camera.center)(0.0, 0.0)
            self.camera.zoom = config.DEFAULT_ZOOM
            return True
        return False

    # -- drawing ----------------------------------------------------------

    def _draw(self) -> None:
        self.camera.viewport = self.surface.get_size()
        self.surface.fill(config.Color.BACKGROUND)
        draw_grid(self.surface, self.camera)
        self.scene.draw(self.surface)
        if self.show_hud:
            self.hud.draw(self.surface, self._hud_lines(), self.scene.hud_origin)
        pygame.display.flip()

    def _hud_lines(self) -> list[str]:
        return self.scene.hud_lines() + [
            f"# {self.clock.get_fps():4.0f} fps   zoom {self.camera.zoom:6.2f} px/m",
            "# WASD/arrows or screen edge pan   middle-drag pan   wheel zoom"
            "   [Home] reset   [F1] hud   [Esc] quit",
        ]
