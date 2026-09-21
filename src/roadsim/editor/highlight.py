"""Something in the network the cursor is about to act on, as data.

A hover highlight answers "which road, which node" before the click, the way
a game road tool lights up the segment you are about to connect to. It is an
*id*, not geometry: the overlay looks the thing up and draws its real outline,
so a highlight can never drift from the road it names, and a test can assert
what is lit with no window open.

Distinct from a `Snap`, which says where a road would end, and from a
`PreviewHandle`, which is a point you can grab. A highlight is the whole thing
under the cursor.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class HighlightKind(Enum):
    NODE = "node"
    SEGMENT = "segment"


@dataclass(frozen=True, slots=True)
class Highlight:
    kind: HighlightKind
    id: int

    @staticmethod
    def node(node_id: int) -> Highlight:
        return Highlight(HighlightKind.NODE, node_id)

    @staticmethod
    def segment(segment_id: int) -> Highlight:
        return Highlight(HighlightKind.SEGMENT, segment_id)
