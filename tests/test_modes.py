"""Modes over one shared world.

The claim being tested is the one the whole arrangement rests on: a mode is a way
of *using* the world, not a copy of it. So switching must not disturb the network,
the history or the selection, and a mode that says it does not edit must not be
able to - which is asserted by driving it and checking the save payload is
untouched, not by reading the code and believing it.
"""

from __future__ import annotations

import pygame
import pytest

from roadsim.editor.context import Selection
from roadsim.geometry import Vec2
from roadsim.modes import MODES, ModeBox, RoadMode, ViewMode
from roadsim.render.camera import Camera
from roadsim.road.network import RoadNetwork
from roadsim.road.presets import ONE_WAY_TWO_LANE, RESIDENTIAL_TWO_WAY
from roadsim.scenes.game import GameScene
from roadsim.serialization import dumps

VIEWPORT = (1440, 900)


@pytest.fixture
def scene() -> GameScene:
    network = RoadNetwork()
    network.connect(Vec2(-60.0, 0.0), Vec2(60.0, 0.0), RESIDENTIAL_TWO_WAY)
    network.rebuild_all()
    scene = GameScene(Camera(zoom=8.0, viewport=VIEWPORT), network)
    scene.ui.layout(VIEWPORT)
    return scene


def key(code: int, mod: int = 0) -> pygame.event.Event:
    return pygame.event.Event(pygame.KEYDOWN, key=code, mod=mod)


def road_index() -> int:
    return [cls.name for cls in MODES].index(RoadMode.name)


def to_roads(scene: GameScene) -> RoadMode:
    scene._select_mode(road_index())
    return scene.modes.active


# -- the registry ----------------------------------------------------------


def test_the_app_opens_in_view_mode(scene):
    """Looking before touching: an accidental first click must not build a road."""
    assert scene.modes.active.name == ViewMode.name


def test_every_registered_mode_can_be_entered_and_left(scene):
    for index in range(len(MODES)):
        scene._select_mode(index)
        assert scene.modes.active_index == index


def test_selecting_the_active_mode_again_does_nothing(scene):
    before = scene.modes.active
    scene._select_mode(scene.modes.active_index)
    assert scene.modes.active is before


def test_an_index_outside_the_registry_is_ignored(scene):
    box = ModeBox([cls() for cls in MODES], scene.ctx)
    box.select(99)
    assert box.active_index == 0


# -- switching leaves the world alone --------------------------------------


def test_switching_modes_keeps_the_same_world(scene):
    network, before = scene.ctx.network, dumps(scene.ctx.network)
    for index in (road_index(), 0, road_index()):
        scene._select_mode(index)
    assert scene.ctx.network is network
    assert dumps(scene.ctx.network) == before


def test_switching_modes_keeps_the_undo_history(scene):
    roads = to_roads(scene)
    roads.toolbox.select(3)  # profile brush
    scene.ctx.select_profile(ONE_WAY_TWO_LANE.name)  # painting on like for like
    roads.toolbox.active.paint(scene.ctx, Vec2(0.0, 0.1))  # records nothing
    depth = scene.ctx.history.depth
    assert depth == 1

    scene._select_mode(0)
    scene._select_mode(road_index())
    assert scene.ctx.history.depth == depth


def test_leaving_mid_road_abandons_it_without_mutating_anything(scene):
    """Points left on the cursor would reappear later attached to a cursor that
    has since moved - so leaving drops them, and drops nothing else."""
    before = dumps(scene.ctx.network)
    roads = to_roads(scene)
    roads.toolbox.select(1)  # draw
    draw = roads.toolbox.active
    draw.points.extend([Vec2(0.0, 40.0), Vec2(40.0, 40.0)])

    scene._select_mode(0)
    assert draw.points == []
    assert dumps(scene.ctx.network) == before
    assert scene.ctx.history.depth == 0


# -- view mode cannot edit -------------------------------------------------


def test_view_mode_clicks_inspect_and_never_mutate(scene):
    before = dumps(scene.ctx.network)
    view = scene.modes.active

    for pos in ((720, 450), (300, 200), (900, 700)):
        view.handle_event(pygame.event.Event(pygame.MOUSEMOTION, pos=pos), scene.ctx)
        view.handle_event(
            pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=pos), scene.ctx
        )

    assert dumps(scene.ctx.network) == before
    assert scene.ctx.history.depth == 0


def test_view_mode_reports_what_is_under_the_cursor(scene):
    view = scene.modes.active
    on_the_road = scene.camera.to_screen(Vec2(0.0, 0.0))
    view.handle_event(
        pygame.event.Event(pygame.MOUSEMOTION, pos=(int(on_the_road[0]), int(on_the_road[1]))),
        scene.ctx,
    )
    assert view.hover.segment == 1

    view.handle_event(pygame.event.Event(pygame.MOUSEMOTION, pos=(5, 5)), scene.ctx)
    assert view.hover.is_empty


# -- keys ------------------------------------------------------------------


def test_shift_and_a_digit_switches_mode(scene):
    assert scene.handle_event(key(pygame.K_2, pygame.KMOD_SHIFT))
    assert scene.modes.active_index == 1


def test_a_plain_digit_belongs_to_the_active_modes_tools(scene):
    """Which is exactly why the mode switch is on Shift."""
    roads = to_roads(scene)
    scene.handle_event(key(pygame.K_3))
    assert roads.toolbox.active_index == 2
    assert scene.modes.active is roads


def test_tab_cycles_the_road_type_from_any_mode(scene):
    first = scene.ctx.profile.name
    assert scene.handle_event(key(pygame.K_TAB))
    assert scene.ctx.profile.name != first


def test_delete_removes_the_selection_as_one_undo_step(scene):
    scene.ctx.select(Selection(segment=1))
    assert scene.handle_event(key(pygame.K_DELETE))
    assert 1 not in scene.ctx.network.segments
    assert scene.ctx.history.depth == 1

    scene.ctx.undo()
    assert 1 in scene.ctx.network.segments


def test_undo_and_redo_reach_the_scene_from_any_mode(scene):
    before = dumps(scene.ctx.network)
    roads = to_roads(scene)
    roads.toolbox.select(3)
    scene.ctx.select_profile(ONE_WAY_TWO_LANE.name)
    roads.toolbox.active.paint(scene.ctx, Vec2(0.0, 0.1))

    scene.handle_event(key(pygame.K_z, pygame.KMOD_CTRL))
    scene.ctx.network.rebuild_dirty()
    assert dumps(scene.ctx.network) == before

    scene.handle_event(key(pygame.K_z, pygame.KMOD_CTRL | pygame.KMOD_SHIFT))
    assert scene.ctx.network.segments[1].profile is ONE_WAY_TWO_LANE


# -- the interface follows the mode ---------------------------------------


def test_each_mode_brings_its_own_widgets(scene):
    view_widgets = len(scene.ui.widgets)
    to_roads(scene)
    assert len(scene.ui.widgets) > view_widgets  # road bar and tool row arrived


def test_the_mode_row_survives_every_switch(scene):
    for index in (road_index(), 0, road_index(), 0):
        scene._select_mode(index)
        assert scene.ui.widgets[0].children[0].label == MODES[0].name


def test_replacing_the_network_keeps_the_interface_working(scene):
    to_roads(scene)
    scene._replace(RoadNetwork(), "empty")
    assert scene.ctx.network.segments == {}
    assert scene.modes.active.toolbox.ctx is scene.ctx
    assert scene.ui.widgets
