"""A titled box of text lines, sized to its contents.

The same trick as the HUD - a line starting with `#` is dimmed - so the lines a
tool or a mode already produces can be shown either way round without either side
learning about the other.

The panel *reads* its lines through a callable rather than being handed them, for
the same reason a button asks whether it is active: the thing it describes changes
without the panel being told.
"""

from __future__ import annotations

from collections.abc import Callable

import pygame

from .. import config
from .theme import Theme
from .widget import Widget

Lines = Callable[[], list[str]]


class Panel(Widget):
    def __init__(
        self,
        lines: Lines,
        title: str = "",
        anchor_right: bool = False,
        width: float = 280.0,
        offset: tuple[float, float] = (0.0, 0.0),
    ) -> None:
        super().__init__()
        self.lines = lines
        self.title = title
        self.anchor_right = anchor_right
        self.width = width
        self.offset = offset
        self._rendered: list[pygame.Surface] = []

    def layout(self, viewport: pygame.Rect) -> None:
        self._viewport = pygame.Rect(viewport)
        # Height follows the content, so the panel is measured at draw time and
        # `rect` is what was last drawn. A panel claiming space it is not using
        # would block the map underneath it.
        self.rect = pygame.Rect(0, 0, 0, 0)

    def draw(self, surface: pygame.Surface, theme: Theme) -> None:
        lines = self.lines()
        if not lines:
            self.rect = pygame.Rect(0, 0, 0, 0)
            return

        font = theme.font()
        spacing = font.get_linesize()
        rendered = [_render(font, theme, line) for line in lines]
        heading = (
            theme.small.render(self.title, True, config.Color.UI_TEXT_DIM)
            if self.title
            else None
        )

        pad = int(theme.padding)
        width = int(max(self.width, max(s.get_width() for s in rendered) + pad * 2))
        height = spacing * len(rendered) + pad * 2 + (spacing if heading else 0)

        dx, dy = self.offset
        left = (
            self._viewport.right - width - pad - dx
            if self.anchor_right
            else self._viewport.left + pad + dx
        )
        self.rect = pygame.Rect(int(left), int(self._viewport.top + pad + dy), width, height)

        box = pygame.Surface(self.rect.size, pygame.SRCALPHA)
        box.fill((*config.Color.UI_PANEL, 224))
        surface.blit(box, self.rect.topleft)
        pygame.draw.rect(
            surface, config.Color.UI_PANEL_EDGE, self.rect, 1, border_radius=theme.radius
        )

        y = self.rect.top + pad
        if heading is not None:
            surface.blit(heading, (self.rect.left + pad, y))
            y += spacing
        for text in rendered:
            surface.blit(text, (self.rect.left + pad, y))
            y += spacing


def _render(font: pygame.font.Font, theme: Theme, line: str) -> pygame.Surface:
    dim = line.startswith("#")
    text = line[1:].lstrip() if dim else line
    color = config.Color.UI_TEXT_DIM if dim else config.Color.UI_TEXT
    return font.render(text, True, color)
