"""Which modifier keys are down, read once per use.

`config.py` imports nothing - not even pygame - and must stay that way, so the
key constants live here instead. Every tool asks `Modifiers.current()` rather
than reaching for `pygame.key.get_mods()` itself, which is what keeps the
binding for a gesture in one place: changing what "snap the curve" is held with
is a one-line change to `CURVE_SNAP_MOD`, not a search through `tools/`.

Read live, never from a `KEYDOWN`/`KEYUP` pair. Alt in particular raises the
window menu on some platforms and its key events can be eaten before a tool sees
them; the *state* is always readable.
"""

from __future__ import annotations

from dataclasses import dataclass

import pygame

CURVE_SNAP_MOD = pygame.KMOD_ALT
"""Held to snap a curve to tidy values while dragging. One name to change if
Alt turns out to be unusable on a platform."""


@dataclass(frozen=True, slots=True)
class Modifiers:
    shift: bool = False
    alt: bool = False
    ctrl: bool = False

    @staticmethod
    def current() -> "Modifiers":
        """With no window open - a test driving a tool directly - nothing is
        held. That is the truth, not a fallback: a modifier is a live keyboard
        state, and there is no keyboard. Returning it rather than raising is
        what lets a tool ask unconditionally instead of guarding the call."""
        if not pygame.get_init() or not pygame.display.get_init():
            return Modifiers()
        mods = pygame.key.get_mods()
        return Modifiers(
            shift=bool(mods & pygame.KMOD_SHIFT),
            alt=bool(mods & CURVE_SNAP_MOD),
            ctrl=bool(mods & pygame.KMOD_CTRL),
        )
