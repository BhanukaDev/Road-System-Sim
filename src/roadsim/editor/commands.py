"""Every network mutation, as an object that can undo itself (D6).

Nothing else in the editor may touch `RoadNetwork`. Tools build commands and
hand them to `History`; that is the whole contract, and it is what makes undo
free rather than retrofitted.

Two rules make undo trustworthy here:

* **Commands remember their ids.** Redoing an add re-uses the id the first do
  allocated, so a do/undo/redo cycle produces a byte-identical save rather than
  a network that merely looks the same.
* **Commands capture what they are about to destroy**, not what they expect to
  find. A remove stores the segment it removed; it does not reconstruct one from
  the tool's intent.

Nothing here rebuilds junctions. Mutations mark nodes dirty and the scene calls
`rebuild_dirty()` once a frame - never mid-command.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from ..geometry import Vec2
from ..road.network import RoadNetwork
from ..road.profile import RoadProfile
from ..road.segment import RoadSegment


class Command(ABC):
    """One named, reversible change."""

    label: str = "change"

    @abstractmethod
    def do(self, network: RoadNetwork) -> None: ...

    @abstractmethod
    def undo(self, network: RoadNetwork) -> None: ...

    def __str__(self) -> str:
        return self.label


class NodeSlot:
    """A node id one command produces and a later one consumes.

    The draw tool cannot know the id of a node that a split, earlier in the same
    composite, has not created yet. A slot lets the commands stay independent
    without either of them reaching into the network to guess.
    """

    __slots__ = ("node_id",)

    def __init__(self, node_id: int | None = None) -> None:
        self.node_id = node_id

    def resolve(self) -> int:
        if self.node_id is None:
            raise ValueError("node slot was read before it was filled")
        return self.node_id

    def __repr__(self) -> str:
        return f"NodeSlot({self.node_id})"


@dataclass(frozen=True, slots=True)
class _SegmentState:
    """Everything authoritative about a segment, enough to rebuild it exactly."""

    id: int
    node_a: int
    node_b: int
    control_points: tuple[Vec2, ...]
    profile: RoadProfile
    corner_radius: float
    profile_b: RoadProfile | None = None

    @staticmethod
    def capture(segment: RoadSegment) -> _SegmentState:
        return _SegmentState(
            segment.id,
            segment.node_a,
            segment.node_b,
            tuple(segment.control_points),
            segment.profile,
            segment.corner_radius,
            segment.profile_b,
        )

    def restore(self, network: RoadNetwork) -> RoadSegment:
        return network.add_segment(
            self.node_a,
            self.node_b,
            list(self.control_points),
            self.profile,
            corner_radius=self.corner_radius,
            segment_id=self.id,
            profile_b=self.profile_b,
        )


# -- nodes -----------------------------------------------------------------


@dataclass
class CreateNode(Command):
    """Put a free node down. Usually one step of a composite draw."""

    position: Vec2
    slot: NodeSlot = field(default_factory=NodeSlot)
    label: str = "create node"
    _id: int | None = field(default=None, init=False, repr=False)

    def do(self, network: RoadNetwork) -> None:
        node = network.add_node(self.position, node_id=self._id)
        self._id = node.id
        self.slot.node_id = node.id

    def undo(self, network: RoadNetwork) -> None:
        network.remove_node(self._id)


@dataclass
class MoveNode(Command):
    node_id: int
    position: Vec2
    label: str = "move node"
    _was: Vec2 | None = field(default=None, init=False, repr=False)

    def do(self, network: RoadNetwork) -> None:
        if self._was is None:
            self._was = network.nodes[self.node_id].position
        network.move_node(self.node_id, self.position)

    def undo(self, network: RoadNetwork) -> None:
        network.move_node(self.node_id, self._was)


@dataclass
class RemoveNode(Command):
    """Delete a node and, with it, every segment that ended there."""

    node_id: int
    label: str = "delete node"
    _position: Vec2 | None = field(default=None, init=False, repr=False)
    _segments: tuple[_SegmentState, ...] = field(default=(), init=False, repr=False)

    def do(self, network: RoadNetwork) -> None:
        node = network.nodes[self.node_id]
        self._position = node.position
        self._segments = tuple(
            _SegmentState.capture(network.segments[sid]) for sid in sorted(node.segments)
        )
        network.remove_node(self.node_id)

    def undo(self, network: RoadNetwork) -> None:
        network.add_node(self._position, node_id=self.node_id)
        for state in self._segments:
            state.restore(network)


@dataclass
class MergeNodes(Command):
    """Fold `dragged_id` into `target_id` - the only way two separately drawn
    roads become one real junction (D20). Every segment `dragged_id` touched
    still exists afterwards, only rewired, so undo restores their node
    references and control points directly rather than through
    `_SegmentState.restore` - that method re-`add_segment`s, which would
    collide with a segment id `merge_nodes` never actually freed."""

    dragged_id: int
    target_id: int
    label: str = "connect road"
    _position: Vec2 | None = field(default=None, init=False, repr=False)
    _segments: tuple[_SegmentState, ...] | None = field(
        default=None, init=False, repr=False
    )

    def do(self, network: RoadNetwork) -> None:
        if self._position is None:
            node = network.nodes[self.dragged_id]
            self._position = node.position
            self._segments = tuple(
                _SegmentState.capture(network.segments[sid])
                for sid in sorted(node.segments)
            )
        network.merge_nodes(self.dragged_id, self.target_id)

    def undo(self, network: RoadNetwork) -> None:
        network.add_node(self._position, node_id=self.dragged_id)
        dragged, target = network.nodes[self.dragged_id], network.nodes[self.target_id]
        for state in self._segments:
            segment = network.segments[state.id]
            segment.node_a, segment.node_b = state.node_a, state.node_b
            segment.control_points = list(state.control_points)
            segment.refit()
            target.segments.discard(state.id)
            dragged.segments.add(state.id)
            network._touch_ends(segment)


# -- segments --------------------------------------------------------------


@dataclass
class AddSegment(Command):
    """Join two nodes, each named by a slot so splits can feed into it."""

    node_a: NodeSlot
    node_b: NodeSlot
    control_points: list[Vec2]
    profile: RoadProfile
    corner_radius: float | None = None
    label: str = "draw road"
    profile_b: RoadProfile | None = None
    """Makes the segment a lane-change taper to this section at B (D26)."""
    _id: int | None = field(default=None, init=False, repr=False)

    def do(self, network: RoadNetwork) -> None:
        segment = network.add_segment(
            self.node_a.resolve(),
            self.node_b.resolve(),
            list(self.control_points),
            self.profile,
            corner_radius=self.corner_radius,
            segment_id=self._id,
            profile_b=self.profile_b,
        )
        self._id = segment.id

    def undo(self, network: RoadNetwork) -> None:
        network.remove_segment(self._id)


@dataclass
class RemoveSegment(Command):
    """Delete a segment, taking any node it orphans with it.

    Leaving a stranded degree-zero node behind would be invisible on screen and
    would still save to disk, so the cleanup is part of the command - and comes
    back on undo.
    """

    segment_id: int
    label: str = "delete road"
    _state: _SegmentState | None = field(default=None, init=False, repr=False)
    _orphans: tuple[tuple[int, Vec2], ...] = field(default=(), init=False, repr=False)

    def do(self, network: RoadNetwork) -> None:
        segment = network.segments[self.segment_id]
        self._state = _SegmentState.capture(segment)
        ends = {segment.node_a, segment.node_b}
        network.remove_segment(self.segment_id)
        orphans = [nid for nid in sorted(ends) if not network.nodes[nid].segments]
        self._orphans = tuple((nid, network.nodes[nid].position) for nid in orphans)
        for nid, _ in self._orphans:
            network.remove_node(nid)

    def undo(self, network: RoadNetwork) -> None:
        for nid, position in self._orphans:
            network.add_node(position, node_id=nid)
        self._state.restore(network)


@dataclass
class SetProfile(Command):
    segment_id: int
    profile: RoadProfile
    label: str = "set profile"
    _was: RoadProfile | None = field(default=None, init=False, repr=False)

    def do(self, network: RoadNetwork) -> None:
        if self._was is None:
            self._was = network.segments[self.segment_id].profile
        network.set_profile(self.segment_id, self.profile)

    def undo(self, network: RoadNetwork) -> None:
        network.set_profile(self.segment_id, self._was)


@dataclass
class SetControlPoints(Command):
    """Reshape a placed road - what `editor/tools/shape_road.py` drags with.

    `network.set_control_points` re-pins both endpoints to the nodes, so this
    can never detach a road from its junction; nothing here needs to repeat
    that check."""

    segment_id: int
    control_points: list[Vec2]
    label: str = "reshape road"
    _was: tuple[Vec2, ...] | None = field(default=None, init=False, repr=False)

    def do(self, network: RoadNetwork) -> None:
        if self._was is None:
            self._was = tuple(network.segments[self.segment_id].control_points)
        network.set_control_points(self.segment_id, list(self.control_points))

    def undo(self, network: RoadNetwork) -> None:
        network.set_control_points(self.segment_id, list(self._was))


@dataclass
class SetCornerRadius(Command):
    """Dragging a fillet's `ARC_END` handle - one radius for the whole road."""

    segment_id: int
    radius: float
    label: str = "set corner radius"
    _was: float | None = field(default=None, init=False, repr=False)

    def do(self, network: RoadNetwork) -> None:
        if self._was is None:
            self._was = network.segments[self.segment_id].corner_radius
        network.set_corner_radius(self.segment_id, self.radius)

    def undo(self, network: RoadNetwork) -> None:
        network.set_corner_radius(self.segment_id, self._was)


@dataclass
class SplitSegment(Command):
    """Cut a segment in two at arc length `s`. Drawing onto a road does this.

    The first `do` asks the network to split and records exactly what came out;
    every later redo replays those recorded pieces rather than re-splitting, so
    a redo cannot drift from the do it is repeating.
    """

    segment_id: int
    s: float
    slot: NodeSlot = field(default_factory=NodeSlot)
    label: str = "split road"
    _was: _SegmentState | None = field(default=None, init=False, repr=False)
    _node: tuple[int, Vec2] | None = field(default=None, init=False, repr=False)
    _halves: tuple[_SegmentState, ...] = field(default=(), init=False, repr=False)

    def do(self, network: RoadNetwork) -> None:
        self._was = _SegmentState.capture(network.segments[self.segment_id])
        if self._node is None:
            first, second, mid = network.split_segment(self.segment_id, self.s)
            self._node = (mid, network.nodes[mid].position)
            self._halves = (
                _SegmentState.capture(network.segments[first]),
                _SegmentState.capture(network.segments[second]),
            )
        else:
            network.remove_segment(self.segment_id)
            network.add_node(self._node[1], node_id=self._node[0])
            for half in self._halves:
                half.restore(network)
        self.slot.node_id = self._node[0]

    def undo(self, network: RoadNetwork) -> None:
        # Removing the node takes both halves with it.
        network.remove_node(self._node[0])
        self._was.restore(network)

    @property
    def new_node_id(self) -> int | None:
        return None if self._node is None else self._node[0]


# -- composition -----------------------------------------------------------


@dataclass
class Composite(Command):
    """Several commands as one undo step. Undone in reverse, always."""

    commands: list[Command]
    label: str = "edit"

    def do(self, network: RoadNetwork) -> None:
        done: list[Command] = []
        try:
            for command in self.commands:
                command.do(network)
                done.append(command)
        except Exception:
            # A half-applied composite is worse than a failed one.
            for command in reversed(done):
                command.undo(network)
            raise

    def undo(self, network: RoadNetwork) -> None:
        for command in reversed(self.commands):
            command.undo(network)


# -- history ---------------------------------------------------------------


class History:
    """Undo and redo stacks. The only thing a tool is allowed to push to."""

    def __init__(self, network: RoadNetwork, limit: int = 200) -> None:
        self.network = network
        self.limit = limit
        self._undo: list[Command] = []
        self._redo: list[Command] = []

    def push(self, command: Command) -> Command:
        """Run a command and make it undoable. Clears the redo stack."""
        command.do(self.network)
        self._undo.append(command)
        del self._undo[: max(0, len(self._undo) - self.limit)]
        self._redo.clear()
        return command

    def undo(self) -> Command | None:
        if not self._undo:
            return None
        command = self._undo.pop()
        command.undo(self.network)
        self._redo.append(command)
        return command

    def redo(self) -> Command | None:
        if not self._redo:
            return None
        command = self._redo.pop()
        command.do(self.network)
        self._undo.append(command)
        return command

    def clear(self) -> None:
        """Forget everything - after a load, where the old stack means nothing."""
        self._undo.clear()
        self._redo.clear()

    @property
    def can_undo(self) -> bool:
        return bool(self._undo)

    @property
    def can_redo(self) -> bool:
        return bool(self._redo)

    @property
    def undo_label(self) -> str | None:
        return self._undo[-1].label if self._undo else None

    @property
    def redo_label(self) -> str | None:
        return self._redo[-1].label if self._redo else None

    @property
    def depth(self) -> int:
        return len(self._undo)
