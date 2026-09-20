"""A strip of widgets pinned to an edge of the window.

Bars own layout and nothing else: they take the viewport, claim a band of it, and
hand each child an equal slot. `Anchor` keeps the arithmetic in one place so a new
bar is a construction rather than a set of magic offsets.
"""

from __future__ import annotations

from enum import Enum

import pygame

from .. import config
from .theme import Theme
from .widget import Container, Widget


class Anchor(Enum):
    TOP = "top"
    BOTTOM = "bottom"


class Bar(Container):
    def __init__(
        self,
        children: list[Widget],
        anchor: Anchor = Anchor.BOTTOM,
        height: float = config.UI_ROW_HEIGHT,
        item_width: float = config.UI_ROW_BUTTON_WIDTH,
        offset: float = 0.0,
        centred: bool = False,
        title: str = "",
    ) -> None:
        super().__init__(children)
        self.anchor = anchor
        self.height = height
        self.item_width = item_width
        self.offset = offset
        """Pixels in from the anchored edge - how rows stack without overlapping."""
        self.centred = centred
        self.title = title
        self._content = pygame.Rect(0, 0, 0, 0)
        """The drawn panel, which is narrower than the band. Set by `layout`."""

    # -- layout ------------------------------------------------------------

    def layout(self, viewport: pygame.Rect) -> None:
        pad = config.UI_PADDING
        gap = config.UI_GAP
        band_height = self.height + pad * 2
        top = (
            viewport.top + self.offset
            if self.anchor is Anchor.TOP
            else viewport.bottom - self.offset - band_height
        )

        count = len(self.children)
        span = count * self.item_width + max(0, count - 1) * gap
        title_width = 0.0
        if self.title:
            title_width = self.item_width * 0.55

        left = viewport.left + pad + title_width
        if self.centred:
            left = viewport.centerx - span / 2.0

        self.rect = pygame.Rect(
            int(viewport.left),
            int(top),
            int(viewport.width),
            int(band_height),
        )
        self._content = pygame.Rect(
            int(left - title_width),
            int(top),
            int(span + title_width + pad * 2),
            int(band_height),
        )

        for i, child in enumerate(self.children):
            child.layout(
                pygame.Rect(
                    int(left + i * (self.item_width + gap)),
                    int(top + pad),
                    int(self.item_width),
                    int(self.height),
                )
            )

    def contains(self, pos: tuple[int, int]) -> bool:
        """Only the drawn panel blocks the world, not the whole width of the band.

        A bar that claimed its entire row would stop the user drawing a road in
        the empty space beside three buttons, which reads as the map being dead.
        """
        return self._content.collidepoint(pos)

    # -- drawing -----------------------------------------------------------

    def draw(self, surface: pygame.Surface, theme: Theme) -> None:
        panel = pygame.Surface(self._content.size, pygame.SRCALPHA)
        panel.fill((*config.Color.UI_PANEL, 232))
        surface.blit(panel, self._content.topleft)
        pygame.draw.rect(
            surface,
            config.Color.UI_PANEL_EDGE,
            self._content,
            1,
            border_radius=theme.radius,
        )
        if self.title:
            label = theme.small.render(self.title, True, config.Color.UI_TEXT_DIM)
            surface.blit(
                label,
                label.get_rect(
                    midleft=(self._content.left + config.UI_PADDING, self._content.centery)
                ),
            )
        super().draw(surface, theme)
