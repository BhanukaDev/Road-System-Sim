"""The network one command ahead of itself - what a preview actually shows.

A road being drawn is not a road yet, but the honest way to show what it *will*
be is to build it: copy the network, apply the command, rebuild the junctions
the change touched, and draw the result translucently over the real thing.
That is what Cities: Skylines' ghost is doing, and it is why its ghost shows
the junction that will form and not just a strip following the cursor.

Doing it this way means the preview and the commit cannot disagree. The trims,
the caps, the turning head at a dead end, a junction that comes out degenerate -
every one of those is derived by the same `rebuild_dirty` the scene runs after
a real commit, on the same kind of network, from a command built by the same
function. Validity is read off the ghost's own flags (`road/validate.py`), not
computed by a second rule set that could drift from the renderer's.

The real network is never touched. `RoadNetwork.copy()` shares immutable
profiles and copies everything else, and the command object is applied to the
copy only - the caller builds a fresh one for the commit, because a command
remembers the ids it allocated (`editor/commands.py`) and a second `do` would
be a redo, not a first do.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..road.network import RoadNetwork
from ..road.validate import Problem, check
from .commands import Command


@dataclass(frozen=True, slots=True)
class Ghost:
    network: RoadNetwork
    """A copy with the command applied and its dirty junctions rebuilt."""
    segments: frozenset[int]
    """Segments the change created or re-trimmed. What the overlay draws."""
    nodes: frozenset[int]
    """Nodes the change created or whose junction or cap was rebuilt."""
    new_segments: frozenset[int]
    """The subset of `segments` that did not exist before."""
    problem: Problem | None = None

    @property
    def invalid(self) -> bool:
        return self.problem is not None

    @property
    def reason(self) -> str:
        return self.problem.reason if self.problem else ""


def ghost_of(network: RoadNetwork, command: Command) -> Ghost:
    """Apply `command` to a copy of `network` and report what it would change.

    The dirty set the command leaves behind is the change's own footprint:
    `rebuild_dirty` retrims exactly the segments at those nodes, so the same set
    scopes both the rebuild and the drawing. Read before the rebuild clears it.
    """
    scratch = network.copy()
    before = set(scratch.segments)
    command.do(scratch)
    dirty = set(scratch.dirty_nodes)
    touched: set[int] = set()
    for node_id in dirty:
        node = scratch.nodes.get(node_id)
        if node is not None:
            touched.update(node.segments)
    scratch.rebuild_dirty()

    segments = frozenset(touched)
    nodes = frozenset(nid for nid in dirty if nid in scratch.nodes)
    new = frozenset(sid for sid in segments if sid not in before)
    return Ghost(
        scratch,
        segments,
        nodes,
        new,
        check(scratch, segments, nodes, new),
    )
