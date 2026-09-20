"""A rectangle plus a function.

`is_active` is a callable rather than a flag because what a button reflects - the
selected road type, the active tool, the current mode - lives in the editor and
changes without the button being told. Asking at draw time means the interface can
never disagree with the state it is showing, which is the failure mode a cached
flag produces the first time a keyboard shortcut changes the same thing.

Subclasses override `render_content` only; the frame, the states and the hit
testing are settled here.
"""

from __future__ import annotations

from collections.abc import Callable

import pygame

from .. import config
from .theme import Theme, fit_text
from .widget import Widget

Action = Callable[[], None]
Predicate = Callable[[], bool]


def _never() -> bool:
    return False


class Button(Widget):
    def __init__(
        self,
        label: str,
        on_click: Action,
        is_active: Predicate = _never,
        hotkey: str = "",
        tooltip: str = "",
    ) -> None:
        super().__init__()
        self.label = label
        self.on_click = on_click
        self.is_active = is_active
        self.hotkey = hotkey
        self.tooltip = tooltip

    @property
    def active(self) -> bool:
        return self.is_active()

    def handle_event(self, event: pygame.event.Event) -> bool:
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.contains(event.pos):
                self.on_click()
                return True
        if event.type == pygame.MOUSEMOTION:
            self.set_hover(event.pos)
            # Never consumed: the bar behind still wants to know, and a motion
            # swallowed here would strand the cursor readout.
        return False

    def draw(self, surface: pygame.Surface, theme: Theme) -> None:
        active = self.active
        pygame.draw.rect(
            surface,
            theme.button_fill(self.hovered, active, self.enabled),
            self.rect,
            border_radius=theme.radius,
        )
        pygame.draw.rect(
            surface,
            config.Color.UI_ACCENT if active else config.Color.UI_BUTTON_EDGE,
            self.rect,
            1,
            border_radius=theme.radius,
        )
        self.render_content(surface, theme, self.rect.inflate(-6, -4))

    # -- overridable -------------------------------------------------------

    def render_content(
        self, surface: pygame.Surface, theme: Theme, inner: pygame.Rect
    ) -> None:
        """Centred label, with the hotkey tucked in the corner."""
        font = theme.font()
        text = font.render(
            fit_text(font, self.label, inner.width),
            True,
            theme.button_text(self.active, self.enabled),
        )
        surface.blit(text, text.get_rect(center=inner.center))
        if self.hotkey:
            hint = theme.small.render(self.hotkey, True, config.Color.UI_TEXT_DIM)
            surface.blit(hint, hint.get_rect(topleft=(inner.left, inner.top)))
