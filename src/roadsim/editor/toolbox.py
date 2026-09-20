"""The tool registry. One line per tool, hotkeys in list order.

This is the whole of rule 2 for the editor: a new tool is a new file under
`tools/` plus one entry in `TOOLS`. Nothing else learns it exists.
"""

from __future__ import annotations

import pygame

from .context import EditorContext, ToolPreview
from .tool import Tool
from .tools.draw_road import DrawRoadTool
from .tools.move_node import MoveNodeTool
from .tools.profile import ProfileTool
from .tools.select import SelectTool

TOOLS: list[type[Tool]] = [
    SelectTool,
    DrawRoadTool,
    MoveNodeTool,
    ProfileTool,
]
"""Order is the hotkey order: 1, 2, 3, ... The first entry is the default."""


class Toolbox:
    def __init__(self, ctx: EditorContext) -> None:
        self.ctx = ctx
        self.tools: list[Tool] = [cls() for cls in TOOLS]
        self.active_index = 0
        self.active.activate(ctx)

    @property
    def active(self) -> Tool:
        return self.tools[self.active_index]

    def select(self, index: int) -> Tool:
        if not 0 <= index < len(self.tools) or index == self.active_index:
            return self.active
        self.active.deactivate(self.ctx)
        self.active_index = index
        self.active.activate(self.ctx)
        self.ctx.status = self.active.name
        return self.active

    def handle_event(self, event: pygame.event.Event) -> bool:
        """Hotkeys first, then the active tool."""
        if event.type == pygame.KEYDOWN and pygame.K_1 <= event.key <= pygame.K_9:
            index = event.key - pygame.K_1
            if index < len(self.tools):
                self.select(index)
                return True
        return self.active.handle_event(event, self.ctx)

    def update(self, dt: float) -> None:
        self.active.update(dt, self.ctx)

    def preview(self) -> ToolPreview:
        return self.active.preview(self.ctx)

    def hud_lines(self) -> list[str]:
        keys = "  ".join(
            f"[{i + 1}]{'*' if i == self.active_index else ' '}{tool.name}"
            for i, tool in enumerate(self.tools)
        )
        return [keys, *self.active.hud_lines(self.ctx)]
