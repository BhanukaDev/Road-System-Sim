"""Window, main loop and the camera controls shared by every scene."""

from __future__ import annotations

import pygame

from . import config
from .render.camera import Camera
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
        self.scene: Scene = SCENES[scene_name](self.camera)
        self.show_hud = True
        self.running = False
        self._panning = False

    def run(self) -> None:
        self.running = True
        while self.running:
            dt = self.clock.tick(config.TARGET_FPS) / 1000.0
            self._pump_events()
            self.scene.update(dt)
            self._draw()
        pygame.quit()

    # -- events -----------------------------------------------------------

    def _pump_events(self) -> None:
        for event in pygame.event.get():
            if self._handle_app_event(event):
                continue
            self.scene.handle_event(event)

    def _handle_app_event(self, event: pygame.event.Event) -> bool:
        """Window and camera control. Returns True if the scene should not see it."""
        if event.type == pygame.QUIT:
            self.running = False
            return True

        if event.type == pygame.VIDEORESIZE:
            self.camera.viewport = (event.w, event.h)
            return True

        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                self.running = False
                return True
            if event.key == pygame.K_F1:
                self.show_hud = not self.show_hud
                return True
            if event.key == pygame.K_HOME:
                self.camera.center = type(self.camera.center)(0.0, 0.0)
                self.camera.zoom = config.DEFAULT_ZOOM
                return True

        if event.type == pygame.MOUSEWHEEL:
            mx, my = pygame.mouse.get_pos()
            factor = config.ZOOM_STEP ** event.y
            self.camera.zoom_at(factor, mx, my)
            return True

        # Middle mouse pans. Left stays free for scene tools.
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 2:
            self._panning = True
            return True
        if event.type == pygame.MOUSEBUTTONUP and event.button == 2:
            self._panning = False
            return True
        if event.type == pygame.MOUSEMOTION and self._panning:
            self.camera.pan_pixels(*event.rel)
            return True

        return False

    # -- drawing ----------------------------------------------------------

    def _draw(self) -> None:
        self.camera.viewport = self.surface.get_size()
        self.surface.fill(config.Color.BACKGROUND)
        draw_grid(self.surface, self.camera)
        self.scene.draw(self.surface)
        if self.show_hud:
            self.hud.draw(self.surface, self._hud_lines())
        pygame.display.flip()

    def _hud_lines(self) -> list[str]:
        return self.scene.hud_lines() + [
            f"# {self.clock.get_fps():4.0f} fps   zoom {self.camera.zoom:6.2f} px/m",
            "# middle-drag pan   wheel zoom   [Home] reset   [F1] hud   [Esc] quit",
        ]
