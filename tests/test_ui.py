"""The interface, with no window open.

Two things are worth pinning down here. The swatch layout is pure arithmetic, so
it is asserted exactly - a strip that overruns its button by a pixel is a layout
that will drift as soon as a profile changes. And every bar is *generated from a
registry*, which the tests check against the registry itself: a hardcoded list of
buttons would pass a count test written by hand, and fail these.
"""

from __future__ import annotations

import pygame
import pytest

from roadsim import config
from roadsim.editor.context import EditorContext
from roadsim.editor.toolbox import TOOLS, Toolbox
from roadsim.geometry import Vec2
from roadsim.modes import MODES
from roadsim.render.camera import Camera
from roadsim.road.network import RoadNetwork
from roadsim.road.presets import ASYMMETRIC_BOULEVARD, PROFILES, RESIDENTIAL_TWO_WAY
from roadsim.ui import UiScreen, mode_bar, road_bar, swatch_rects, tool_bar
from roadsim.ui.theme import THEME, fit_text

from .conftest import approx

VIEWPORT = (1440, 900)


@pytest.fixture
def ctx() -> EditorContext:
    network = RoadNetwork()
    network.connect(Vec2(-60.0, 0.0), Vec2(60.0, 0.0), RESIDENTIAL_TWO_WAY)
    network.rebuild_all()
    return EditorContext(network, Camera(zoom=8.0, viewport=VIEWPORT))


def laid_out(bar):
    bar.layout(pygame.Rect(0, 0, *VIEWPORT))
    return bar


# -- swatches --------------------------------------------------------------


def test_a_swatch_has_one_stripe_per_lane():
    rect = pygame.Rect(0, 0, 120, 16)
    rects = swatch_rects(rect, ASYMMETRIC_BOULEVARD)
    assert len(rects) == len(ASYMMETRIC_BOULEVARD.lanes)


def test_swatch_stripes_run_left_to_right_in_profile_order():
    """Profiles are ordered left to right (D4), and the picture has to agree or it
    teaches the user the road is mirrored."""
    rects = swatch_rects(pygame.Rect(0, 0, 120, 16), ASYMMETRIC_BOULEVARD)
    assert [r.left for r in rects] == sorted(r.left for r in rects)


def test_a_swatch_fills_its_rect_exactly():
    """Not approximately: a strip a pixel proud of its button is the kind of drift
    that only shows up once a profile is added."""
    rect = pygame.Rect(10, 4, 121, 16)
    rects = swatch_rects(rect, ASYMMETRIC_BOULEVARD)
    assert rects[0].left == rect.left
    assert rects[-1].right == rect.right
    assert sum(r.width for r in rects) == rect.width


def test_swatch_stripe_widths_are_proportional_to_lane_widths():
    rect = pygame.Rect(0, 0, 400, 16)
    profile = ASYMMETRIC_BOULEVARD
    rects = swatch_rects(rect, profile)
    for lane, stripe in zip(profile.lanes, rects):
        share = lane.width / profile.total_width
        assert approx(stripe.width, rect.width * share, tol=1.5)


def test_a_narrow_lane_still_gets_visible_width():
    """A bike lane that rounds to nothing defeats the point of the swatch."""
    rects = swatch_rects(pygame.Rect(0, 0, 60, 16), ASYMMETRIC_BOULEVARD)
    assert all(r.width >= 1 for r in rects)


def test_a_swatch_with_no_room_draws_nothing():
    assert swatch_rects(pygame.Rect(0, 0, 0, 16), RESIDENTIAL_TWO_WAY) == []


# -- bars are generated, not written down ----------------------------------


def test_the_road_bar_has_one_button_per_known_profile(ctx):
    bar = road_bar(ctx)
    assert len(bar.children) == len(PROFILES)
    assert [b.profile_name for b in bar.children] == ctx.profile_names


def test_the_tool_bar_has_one_button_per_registered_tool(ctx):
    bar = tool_bar(Toolbox(ctx), offset=0.0)
    assert len(bar.children) == len(TOOLS)
    assert [b.label for b in bar.children] == [cls.name for cls in TOOLS]


def test_the_mode_bar_has_one_button_per_registered_mode():
    names = [cls.name for cls in MODES]
    bar = mode_bar(names, select=lambda i: None, active_index=lambda: 0)
    assert [b.label for b in bar.children] == names


def test_clicking_a_road_button_changes_what_gets_drawn(ctx):
    bar = laid_out(road_bar(ctx))
    target = next(b for b in bar.children if b.profile_name != ctx.profile.name)

    click = pygame.event.Event(
        pygame.MOUSEBUTTONDOWN, button=1, pos=target.rect.center
    )
    assert bar.handle_event(click)
    assert ctx.profile.name == target.profile_name


def test_a_road_button_knows_when_it_is_the_active_one(ctx):
    bar = road_bar(ctx)
    active = [b for b in bar.children if b.active]
    assert [b.profile_name for b in active] == [ctx.profile.name]


def test_a_click_that_misses_every_button_is_not_consumed(ctx):
    bar = laid_out(road_bar(ctx))
    miss = pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=(5, 5))
    assert not bar.handle_event(miss)


def test_a_tool_button_selects_its_tool(ctx):
    toolbox = Toolbox(ctx)
    bar = laid_out(tool_bar(toolbox, offset=0.0))
    last = bar.children[-1]
    bar.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=last.rect.center))
    assert toolbox.active_index == len(TOOLS) - 1


# -- chrome shields the world ---------------------------------------------


def test_the_screen_wants_events_over_chrome_and_not_over_the_world(ctx):
    screen = UiScreen([road_bar(ctx)])
    screen.layout(VIEWPORT)
    bar = screen.widgets[0]

    assert screen.wants(bar.children[0].rect.center)
    assert not screen.wants((VIEWPORT[0] // 2, VIEWPORT[1] // 2))
    assert not screen.wants(None)


def test_the_wheel_over_chrome_never_reaches_the_camera(ctx):
    """Scrolling the road bar must not zoom the map behind it."""
    screen = UiScreen([road_bar(ctx)])
    screen.layout(VIEWPORT)
    over_bar = screen.widgets[0].children[0].rect.center

    screen.handle_event(pygame.event.Event(pygame.MOUSEMOTION, pos=over_bar))
    assert screen.handle_event(pygame.event.Event(pygame.MOUSEWHEEL, y=1, x=0))


def test_the_wheel_over_the_world_passes_straight_through(ctx):
    screen = UiScreen([road_bar(ctx)])
    screen.layout(VIEWPORT)

    screen.handle_event(pygame.event.Event(pygame.MOUSEMOTION, pos=(700, 300)))
    assert not screen.handle_event(pygame.event.Event(pygame.MOUSEWHEEL, y=1, x=0))


def test_an_empty_bar_beside_its_buttons_leaves_the_world_reachable(ctx):
    """A bar that claimed its whole row would kill a wide strip of the map."""
    screen = UiScreen([road_bar(ctx)])
    screen.layout(VIEWPORT)
    bottom_left_corner = (4, VIEWPORT[1] - 20)
    assert not screen.wants(bottom_left_corner)


# -- text ------------------------------------------------------------------


def test_a_long_label_is_shortened_to_fit():
    pygame.font.init()
    font = THEME.small
    long_name = "asymmetric_boulevard"
    fitted = fit_text(font, long_name, 60)
    assert fitted != long_name
    assert font.size(fitted)[0] <= 60


def test_a_label_that_already_fits_is_left_alone():
    pygame.font.init()
    assert fit_text(THEME.small, "car", 400) == "car"


# -- drawing (off-screen, no display) --------------------------------------


def test_the_whole_interface_draws_onto_a_plain_surface(ctx):
    """Cheap, but it is the test that catches a widget reaching for a display."""
    pygame.font.init()
    surface = pygame.Surface(VIEWPORT)
    screen = UiScreen([road_bar(ctx), tool_bar(Toolbox(ctx), offset=config.UI_BAR_HEIGHT)])
    screen.layout(VIEWPORT)
    screen.draw(surface)
