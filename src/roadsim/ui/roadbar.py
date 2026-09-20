"""The bottom bar of road types, built from `road.presets.PROFILES`.

Nothing here knows which roads exist. Add a preset and its button appears, with a
cross-section drawn from its own lanes - which is rule 2 finally paying the
interface as well as the model.
"""

from __future__ import annotations

import pygame

from .. import config
from ..editor.context import EditorContext
from ..road.presets import PROFILES
from .bar import Anchor, Bar
from .button import Button
from .swatch import draw_profile_swatch
from .theme import Theme, fit_text


class RoadButton(Button):
    """A road type: its cross-section, its name, its width."""

    def __init__(self, ctx: EditorContext, name: str, hotkey: str = "") -> None:
        super().__init__(
            name,
            on_click=lambda: ctx.select_profile(name),
            is_active=lambda: ctx.profile.name == name,
            hotkey=hotkey,
        )
        self.ctx = ctx
        self.profile_name = name

    @property
    def profile(self):
        return PROFILES[self.profile_name]

    def render_content(
        self, surface: pygame.Surface, theme: Theme, inner: pygame.Rect
    ) -> None:
        profile = self.profile
        swatch = pygame.Rect(
            inner.left,
            inner.top + 2,
            inner.width,
            int(config.UI_SWATCH_HEIGHT),
        )
        draw_profile_swatch(surface, swatch, profile)

        color = theme.button_text(self.active, self.enabled)
        name = theme.small.render(
            fit_text(theme.small, _short(profile.name), inner.width), True, color
        )
        surface.blit(name, (inner.left, swatch.bottom + 3))

        detail = theme.small.render(
            f"{profile.total_width:.1f} m  {len(profile.lanes)}L",
            True,
            config.Color.UI_TEXT_DIM,
        )
        surface.blit(detail, (inner.left, swatch.bottom + 3 + name.get_height()))


def road_bar(ctx: EditorContext) -> Bar:
    """One button per known profile, in the order the context lists them."""
    buttons = [
        RoadButton(ctx, name, hotkey=str(i + 1) if i < 9 else "")
        for i, name in enumerate(ctx.profile_names)
    ]
    return Bar(
        buttons,
        anchor=Anchor.BOTTOM,
        height=config.UI_BAR_HEIGHT,
        item_width=config.UI_BUTTON_WIDTH,
        centred=True,
    )


def _short(name: str) -> str:
    return name.replace("_", " ")
