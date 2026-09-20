"""Game interface. Sits above `editor`: it drives the editor, never the reverse.

The layering line is `geometry -> road -> render -> editor -> ui -> modes ->
scenes`. Every bar in here is generated from a registry - profiles, tools, modes -
so a new entry anywhere below shows up in the interface without this package
learning its name.
"""

from .bar import Anchor, Bar
from .button import Button
from .panel import Panel
from .roadbar import RoadButton, road_bar
from .screen import UiScreen
from .swatch import draw_profile_swatch, swatch_rects
from .theme import THEME, Theme
from .toolbar import mode_bar, tool_bar
from .widget import Container, Widget

__all__ = [
    "THEME",
    "Anchor",
    "Bar",
    "Button",
    "Container",
    "Panel",
    "RoadButton",
    "Theme",
    "UiScreen",
    "Widget",
    "draw_profile_swatch",
    "mode_bar",
    "road_bar",
    "swatch_rects",
    "tool_bar",
]
