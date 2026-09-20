"""Fonts and metrics, in one place, read from `config`.

Widgets ask the theme for a font and a colour rather than holding their own, so
the whole interface changes from `config.py` like everything else (rule 4). The
theme owns the fonts because `pygame.font.SysFont` is not free and a bar full of
buttons must not build one each.
"""

from __future__ import annotations

import pygame

from .. import config

FONT_STACK = "consolas,menlo,monospace"
"""Same stack as the HUD, so the interface and the readout look related."""


class Theme:
    def __init__(self) -> None:
        self._fonts: dict[int, pygame.font.Font] = {}

    # -- fonts -------------------------------------------------------------

    def font(self, size: int | None = None) -> pygame.font.Font:
        points = config.UI_FONT_SIZE if size is None else size
        if points not in self._fonts:
            self._fonts[points] = pygame.font.SysFont(FONT_STACK, points)
        return self._fonts[points]

    @property
    def small(self) -> pygame.font.Font:
        return self.font(config.UI_FONT_SMALL)

    # -- metrics -----------------------------------------------------------

    @property
    def padding(self) -> float:
        return config.UI_PADDING

    @property
    def gap(self) -> float:
        return config.UI_GAP

    @property
    def radius(self) -> int:
        return config.UI_RADIUS

    # -- colours -----------------------------------------------------------

    def button_fill(self, hovered: bool, active: bool, enabled: bool = True):
        """Active beats hover: what is selected must stay obvious under a cursor
        that happens to be somewhere else."""
        if not enabled:
            return config.Color.UI_PANEL
        if active:
            return config.Color.UI_BUTTON_ACTIVE
        return config.Color.UI_BUTTON_HOVER if hovered else config.Color.UI_BUTTON

    def button_text(self, active: bool, enabled: bool = True):
        if not enabled:
            return config.Color.UI_TEXT_DIM
        return config.Color.UI_TEXT_ACTIVE if active else config.Color.UI_TEXT


def fit_text(font: pygame.font.Font, text: str, width: float) -> str:
    """`text`, shortened until it fits `width`, with an ellipsis if it had to be.

    Buttons are generated from registries, so their labels are whatever the model
    happens to call things - "asymmetric_boulevard" is not going to fit, and a
    label that overruns its button reads as a broken layout rather than a long
    name.
    """
    if font.size(text)[0] <= width:
        return text
    ellipsis = "…"
    trimmed = text
    while trimmed and font.size(trimmed + ellipsis)[0] > width:
        trimmed = trimmed[:-1]
    return trimmed + ellipsis if trimmed else ""


THEME = Theme()
"""The shared instance. One font cache for the whole interface."""
