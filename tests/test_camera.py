"""Camera. Pure maths, no surface needed - the one place world y flips to screen y."""

from __future__ import annotations

import pytest

from roadsim import config
from roadsim.geometry import Vec2
from roadsim.render.camera import Camera

from .conftest import EXACT, assert_vec


@pytest.fixture
def camera() -> Camera:
    return Camera(center=Vec2(10.0, -5.0), zoom=8.0, viewport=(800, 600))


def test_centre_maps_to_the_middle_of_the_viewport(camera):
    sx, sy = camera.to_screen(camera.center)
    assert (abs(sx - 400.0), abs(sy - 300.0)) < (EXACT, EXACT)


def test_world_y_up_becomes_screen_y_down(camera):
    _, above = camera.to_screen(camera.center + Vec2(0.0, 10.0))
    assert above < 300.0


def test_round_trips_between_world_and_screen(camera):
    for point in (Vec2(0.0, 0.0), Vec2(-120.0, 44.0), Vec2(999.0, -3.5)):
        assert_vec(camera.to_world(*camera.to_screen(point)), point, 1e-9)


def test_to_screen_xy_matches_to_screen(camera):
    p = Vec2(-33.0, 12.0)
    assert camera.to_screen_xy(p.x, p.y) == camera.to_screen(p)


def test_zoom_keeps_the_point_under_the_cursor_pinned(camera):
    """Otherwise the world slides away while you are trying to zoom into it."""
    cursor = (620.0, 180.0)
    anchor = camera.to_world(*cursor)
    camera.zoom_at(config.ZOOM_STEP, *cursor)
    assert_vec(camera.to_world(*cursor), anchor, 1e-9)


def test_zoom_is_clamped(camera):
    for _ in range(200):
        camera.zoom_at(2.0, 400.0, 300.0)
    assert camera.zoom <= config.MAX_ZOOM + EXACT
    for _ in range(400):
        camera.zoom_at(0.5, 400.0, 300.0)
    assert camera.zoom >= config.MIN_ZOOM - EXACT


def test_pan_moves_the_world_with_the_mouse(camera):
    """Dragging right must bring world content right, i.e. centre moves left."""
    before = camera.center
    camera.pan_pixels(80.0, 0.0)
    assert camera.center.x < before.x


def test_world_tolerance_shrinks_as_you_zoom_in(camera):
    """Constant screen-space error is what keeps curves smooth at any zoom."""
    coarse = camera.world_tolerance
    camera.zoom *= 4.0
    assert abs(camera.world_tolerance * 4.0 - coarse) <= EXACT


def test_world_bounds_cover_the_viewport(camera):
    lo, hi = camera.world_bounds()
    assert lo.x < camera.center.x < hi.x
    assert lo.y < camera.center.y < hi.y
