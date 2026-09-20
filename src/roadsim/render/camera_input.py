"""Turning input into camera movement. Knows `Camera` and pygame, nothing else.

Pulled out of `app.py` for two reasons. One, the arithmetic was buried in an
event ladder that no test could reach, so panning - the control the user touches
most - was the least covered thing in the app. Two, a drag has *state*, and state
that only a `MOUSEBUTTONUP` inside the window can clear is state that gets stuck:
release the button off-window or alt-tab mid-drag and the camera pans forever.
`cancel()` exists for exactly that, and the window events call it.

Every speed here is in **pixels** per second, converted through `camera.zoom`.
Metres per second would crawl when you are zoomed in and fly when you are zoomed
out, which reads as two different controls rather than one.
"""

from __future__ import annotations

import pygame

from .. import config
from ..geometry import Vec2
from .camera import Camera

PAN_DIRECTIONS: dict[int, Vec2] = {
    pygame.K_w: Vec2(0.0, 1.0),
    pygame.K_UP: Vec2(0.0, 1.0),
    pygame.K_s: Vec2(0.0, -1.0),
    pygame.K_DOWN: Vec2(0.0, -1.0),
    pygame.K_a: Vec2(-1.0, 0.0),
    pygame.K_LEFT: Vec2(-1.0, 0.0),
    pygame.K_d: Vec2(1.0, 0.0),
    pygame.K_RIGHT: Vec2(1.0, 0.0),
}
"""Key to the world direction the *camera* travels. +y is north (D3)."""

PAN_BUTTON = 2
"""Middle. Left belongs to the tools and right is a tool action, so the drag pan
gets the one button nothing else wants."""


class CameraController:
    def __init__(self, camera: Camera) -> None:
        self.camera = camera
        self.dragging = False

    # -- discrete input ----------------------------------------------------

    def handle_event(
        self, event: pygame.event.Event, mouse_pos: tuple[int, int] | None = None
    ) -> bool:
        """Return True if the event was consumed.

        Called *after* the scene, so a tool always gets first refusal on a button.
        """
        if event.type in (pygame.WINDOWFOCUSLOST, pygame.WINDOWLEAVE):
            self.cancel()
            return False  # not ours to consume; other listeners may want it

        if event.type == pygame.MOUSEWHEEL:
            x, y = mouse_pos if mouse_pos is not None else pygame.mouse.get_pos()
            self.camera.zoom_at(config.ZOOM_STEP**event.y, x, y)
            return True

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == PAN_BUTTON:
            self.dragging = True
            return True
        if event.type == pygame.MOUSEBUTTONUP and event.button == PAN_BUTTON:
            self.dragging = False
            return True
        if event.type == pygame.MOUSEMOTION and self.dragging:
            self.camera.pan_pixels(*event.rel)
            return True
        return False

    def cancel(self) -> None:
        """Drop any drag in progress. Focus loss, window leave, mode change."""
        self.dragging = False

    # -- held input --------------------------------------------------------

    def update(
        self,
        dt: float,
        keys=None,
        mouse_pos: tuple[int, int] | None = None,
        viewport: tuple[int, int] | None = None,
    ) -> None:
        """Continuous pan: held keys, then the screen edge.

        Both are `dt`-scaled rather than per-frame, so the camera covers the same
        ground whatever the frame rate.
        """
        step = config.PAN_KEY_SPEED_PX * dt
        if step <= 0.0:
            return
        direction = _held_direction(keys) + _edge_direction(mouse_pos, viewport)
        if direction.length_sq > 0.0:
            self._travel(direction.normalized(), step)

    def _travel(self, direction: Vec2, pixels: float) -> None:
        """Move the camera `pixels` along a unit world direction.

        `pan_pixels` takes a *drag*, and dragging moves the world the opposite way
        to the camera - hence the flipped x. Keeping the transform in `Camera`
        matters more than the sign being pretty (D3).
        """
        self.camera.pan_pixels(-direction.x * pixels, direction.y * pixels)


def _held_direction(keys) -> Vec2:
    if keys is None:
        return Vec2(0.0, 0.0)
    total = Vec2(0.0, 0.0)
    for key, direction in PAN_DIRECTIONS.items():
        if keys[key]:
            total = total + direction
    return total


def _edge_direction(
    mouse_pos: tuple[int, int] | None, viewport: tuple[int, int] | None
) -> Vec2:
    """Which way the cursor's nearness to an edge asks the camera to go.

    A cursor outside the window pans nothing - otherwise the camera would run
    away while you were using another window.
    """
    margin = config.PAN_EDGE_PX
    if mouse_pos is None or viewport is None or margin <= 0.0:
        return Vec2(0.0, 0.0)
    x, y = mouse_pos
    width, height = viewport
    if not (0 <= x < width and 0 <= y < height):
        return Vec2(0.0, 0.0)
    dx = (-1.0 if x < margin else 0.0) + (1.0 if x >= width - margin else 0.0)
    dy = (1.0 if y < margin else 0.0) + (-1.0 if y >= height - margin else 0.0)
    return Vec2(dx, dy)
