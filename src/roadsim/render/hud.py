"""Corner text panel. Deliberately dumb - it renders lines it is handed."""

from __future__ import annotations

import pygame

from .. import config


class Hud:
    def __init__(self, size: int = 15) -> None:
        self.font = pygame.font.SysFont("consolas,menlo,monospace", size)
        self.line_height = self.font.get_linesize()

    def draw(
        self,
        surface: pygame.Surface,
        lines: list[str],
        origin: tuple[int, int] = (12, 10),
        padding: int = 8,
    ) -> None:
        if not lines:
            return
        rendered = [self._render(line) for line in lines]
        width = max(s.get_width() for s in rendered) + padding * 2
        height = self.line_height * len(rendered) + padding * 2

        panel = pygame.Surface((width, height), pygame.SRCALPHA)
        panel.fill((*config.Color.HUD_BACK, 190))
        for i, surf in enumerate(rendered):
            panel.blit(surf, (padding, padding + i * self.line_height))
        surface.blit(panel, origin)

    def _render(self, line: str) -> pygame.Surface:
        """A line starting with '#' is a dimmed heading or hint."""
        dim = line.startswith("#")
        text = line[1:].lstrip() if dim else line
        color = config.Color.HUD_DIM if dim else config.Color.HUD_TEXT
        return self.font.render(text, True, color)
