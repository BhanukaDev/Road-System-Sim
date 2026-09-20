"""Rows built from registries: modes, and the active mode's tools.

Like the road bar, neither row knows what is in it. A new tool is a line in
`editor/toolbox.py` and a new mode a line in `modes/__init__.py`; both then appear
here with a working button and a hotkey hint, because the row is generated from the
same list the hotkeys come from.
"""

from __future__ import annotations

from collections.abc import Callable

from .. import config
from ..editor.toolbox import Toolbox
from .bar import Anchor, Bar
from .button import Button

ModeSwitch = Callable[[int], None]
ModeQuery = Callable[[], int]


def mode_bar(
    names: list[str], select: ModeSwitch, active_index: ModeQuery
) -> Bar:
    """The top row. Hotkeys are Shift+digit, so plain digits stay with the tools."""
    buttons = [
        Button(
            name,
            on_click=lambda i=i: select(i),
            is_active=lambda i=i: active_index() == i,
            hotkey=f"^{i + 1}",
        )
        for i, name in enumerate(names)
    ]
    return Bar(buttons, anchor=Anchor.TOP, title="mode")


def tool_bar(toolbox: Toolbox, offset: float) -> Bar:
    """The active mode's tools, in the order their hotkeys run."""
    buttons = [
        Button(
            tool.name,
            on_click=lambda i=i: toolbox.select(i),
            is_active=lambda i=i: toolbox.active_index == i,
            hotkey=str(i + 1),
        )
        for i, tool in enumerate(toolbox.tools)
    ]
    return Bar(
        buttons,
        anchor=Anchor.BOTTOM,
        offset=offset,
        item_width=config.UI_ROW_BUTTON_WIDTH,
        centred=True,
        title="tool",
    )
