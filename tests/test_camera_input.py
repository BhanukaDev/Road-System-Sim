"""Camera input, driven with synthetic events and no window.

Panning is the control the user touches most and, until this file existed, the
least covered thing in the app - the arithmetic was buried in an event ladder
nothing could reach. Two classes of assertion here: the movement is exactly what
the binding promises, and a drag cannot get stuck.
"""

from __future__ import annotations

import pygame
import pytest

from roadsim import config
from roadsim.geometry import Vec2
from roadsim.render.camera import Camera
from roadsim.render.camera_input import PAN_BUTTON, CameraController

from .conftest import EXACT, approx, assert_vec

VIEWPORT = (800, 600)


@pytest.fixture
def camera() -> Camera:
    return Camera(center=Vec2(0.0, 0.0), zoom=10.0, viewport=VIEWPORT)


@pytest.fixture
def controller(camera) -> CameraController:
    return CameraController(camera)


def event(kind: int, **attrs) -> pygame.event.Event:
    return pygame.event.Event(kind, **attrs)


class _Keys(dict):
    """A stand-in for `pygame.key.get_pressed()` - every key not named is up."""

    def __missing__(self, key) -> bool:
        return False


def keys_down(*keys: int) -> _Keys:
    pressed = _Keys()
    pressed.update({key: True for key in keys})
    return pressed


NONE_HELD = _Keys()


def step_for(dt: float, zoom: float) -> float:
    """How far the camera should travel in world metres. Pixels, over zoom."""
    return config.PAN_KEY_SPEED_PX * dt / zoom


# -- drag pan --------------------------------------------------------------


def test_middle_drag_moves_the_world_with_the_cursor(controller, camera):
    controller.handle_event(event(pygame.MOUSEBUTTONDOWN, button=PAN_BUTTON))
    controller.handle_event(event(pygame.MOUSEMOTION, rel=(40, -30)))

    # Content follows the cursor, so the camera goes the other way - and one
    # pixel of drag is exactly one pixel of world at this zoom.
    assert_vec(camera.center, Vec2(-4.0, -3.0))


def test_motion_without_a_press_does_not_pan(controller, camera):
    assert not controller.handle_event(event(pygame.MOUSEMOTION, rel=(40, 40)))
    assert_vec(camera.center, Vec2(0.0, 0.0))


def test_releasing_the_button_ends_the_drag(controller, camera):
    controller.handle_event(event(pygame.MOUSEBUTTONDOWN, button=PAN_BUTTON))
    controller.handle_event(event(pygame.MOUSEBUTTONUP, button=PAN_BUTTON))
    controller.handle_event(event(pygame.MOUSEMOTION, rel=(50, 50)))
    assert_vec(camera.center, Vec2(0.0, 0.0))


def test_losing_focus_mid_drag_stops_the_pan(controller, camera):
    """The bug this file was written for: a button released off-window never sends
    a MOUSEBUTTONUP, so the camera panned on every later mouse move, forever."""
    controller.handle_event(event(pygame.MOUSEBUTTONDOWN, button=PAN_BUTTON))
    controller.handle_event(event(pygame.WINDOWFOCUSLOST))
    assert not controller.dragging

    controller.handle_event(event(pygame.MOUSEMOTION, rel=(90, 90)))
    assert_vec(camera.center, Vec2(0.0, 0.0))


def test_leaving_the_window_mid_drag_stops_the_pan(controller, camera):
    controller.handle_event(event(pygame.MOUSEBUTTONDOWN, button=PAN_BUTTON))
    controller.handle_event(event(pygame.WINDOWLEAVE))
    controller.handle_event(event(pygame.MOUSEMOTION, rel=(90, 90)))
    assert_vec(camera.center, Vec2(0.0, 0.0))


def test_the_other_buttons_are_left_for_the_tools(controller):
    """The camera takes the middle button precisely so it never eats a tool's."""
    for button in (1, 3):
        assert not controller.handle_event(
            event(pygame.MOUSEBUTTONDOWN, button=button)
        )


# -- keyboard pan ----------------------------------------------------------


def test_held_keys_pan_at_the_configured_speed(controller, camera):
    controller.update(0.5, keys_down(pygame.K_w), None, VIEWPORT)
    assert_vec(camera.center, Vec2(0.0, step_for(0.5, camera.zoom)))


def test_each_key_pans_the_way_it_reads(camera):
    """W is north because world +y is up (D3). A left key that pans right reads
    as the camera being broken."""
    for key, direction in (
        (pygame.K_w, Vec2(0.0, 1.0)),
        (pygame.K_s, Vec2(0.0, -1.0)),
        (pygame.K_a, Vec2(-1.0, 0.0)),
        (pygame.K_d, Vec2(1.0, 0.0)),
        (pygame.K_UP, Vec2(0.0, 1.0)),
        (pygame.K_DOWN, Vec2(0.0, -1.0)),
        (pygame.K_LEFT, Vec2(-1.0, 0.0)),
        (pygame.K_RIGHT, Vec2(1.0, 0.0)),
    ):
        camera.center = Vec2(0.0, 0.0)
        CameraController(camera).update(0.1, keys_down(key), None, VIEWPORT)
        assert_vec(camera.center, direction * step_for(0.1, camera.zoom))


def test_diagonal_pan_is_not_faster_than_straight(controller, camera):
    """Normalising the direction is what stops a diagonal covering 1.41x the
    ground - the classic version of this bug."""
    controller.update(0.25, keys_down(pygame.K_w, pygame.K_d), None, VIEWPORT)
    assert approx(camera.center.length, step_for(0.25, camera.zoom))


def test_opposing_keys_cancel(controller, camera):
    controller.update(0.5, keys_down(pygame.K_a, pygame.K_d), None, VIEWPORT)
    assert_vec(camera.center, Vec2(0.0, 0.0))


def test_pan_speed_is_constant_on_screen_at_any_zoom(camera):
    """Pixels per second, not metres: the same press must cover the same fraction
    of the window whatever the zoom."""
    covered = []
    for zoom in (2.0, 40.0):
        camera.zoom, camera.center = zoom, Vec2(0.0, 0.0)
        CameraController(camera).update(0.2, keys_down(pygame.K_d), None, VIEWPORT)
        covered.append(camera.center.length * zoom)  # back into pixels
    assert approx(covered[0], covered[1])


def test_no_keys_held_moves_nothing(controller, camera):
    controller.update(1.0, NONE_HELD, None, VIEWPORT)
    assert_vec(camera.center, Vec2(0.0, 0.0))


# -- edge pan --------------------------------------------------------------


def test_the_screen_edge_pans_toward_itself(camera):
    inside = config.PAN_EDGE_PX / 2.0
    width, height = VIEWPORT
    for pos, direction in (
        ((inside, height / 2), Vec2(-1.0, 0.0)),
        ((width - inside, height / 2), Vec2(1.0, 0.0)),
        ((width / 2, inside), Vec2(0.0, 1.0)),
        ((width / 2, height - inside), Vec2(0.0, -1.0)),
    ):
        camera.center = Vec2(0.0, 0.0)
        CameraController(camera).update(0.1, NONE_HELD, pos, VIEWPORT)
        assert_vec(camera.center, direction * step_for(0.1, camera.zoom))


def test_the_middle_of_the_window_pans_nothing(controller, camera):
    controller.update(1.0, NONE_HELD, (400, 300), VIEWPORT)
    assert_vec(camera.center, Vec2(0.0, 0.0))


def test_a_cursor_outside_the_window_pans_nothing(controller, camera):
    """Otherwise the camera runs away while you are using another window."""
    controller.update(1.0, NONE_HELD, (-20, 300), VIEWPORT)
    controller.update(1.0, NONE_HELD, (400, 900), VIEWPORT)
    assert_vec(camera.center, Vec2(0.0, 0.0))


def test_edge_pan_is_skipped_when_the_caller_offers_no_cursor(controller, camera):
    """How the app says "the window does not have the mouse"."""
    controller.update(1.0, NONE_HELD, None, VIEWPORT)
    assert_vec(camera.center, Vec2(0.0, 0.0))


# -- zoom ------------------------------------------------------------------


def test_the_wheel_zooms_about_the_cursor(controller, camera):
    cursor = (620, 180)
    anchor = camera.to_world(*cursor)
    assert controller.handle_event(event(pygame.MOUSEWHEEL, y=1, x=0), cursor)
    assert camera.zoom > 10.0
    assert_vec(camera.to_world(*cursor), anchor, EXACT)


def test_the_wheel_zooms_out_as_well(controller, camera):
    controller.handle_event(event(pygame.MOUSEWHEEL, y=-1, x=0), (400, 300))
    assert camera.zoom < 10.0
