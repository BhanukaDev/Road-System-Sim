"""What a tool is allowed to see and do.

A tool gets a context, never the scene. That keeps tools testable without a
window, and it keeps the one mutation rule enforceable in a single place:
`apply()` is the only route to the network, and it goes through `History` (D6).

The context also carries the tool's **preview as data** - paths and points, not
pixels. `editor/overlay.py` is the one place that draws it. So a tool can be
driven from a test with no window open, which is why `Tool` returns a preview
rather than taking a surface the way the M2 sketch suggested (D8).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..geometry import Path, Vec2
from ..render.camera import Camera
from ..road.network import RoadNetwork
from ..road.presets import DEFAULT_PROFILE, PROFILES
from ..road.profile import RoadProfile
from .commands import Command, History
from .guides import Guide
from .snapping import Snap, Snapper


@dataclass(frozen=True, slots=True)
class Selection:
    """What the user has picked. Empty is a valid, common state."""

    node: int | None = None
    segment: int | None = None

    @property
    def is_empty(self) -> bool:
        return self.node is None and self.segment is None

    def describe(self) -> str:
        if self.node is not None:
            return f"node {self.node}"
        if self.segment is not None:
            return f"segment {self.segment}"
        return "nothing"


EMPTY = Selection()


@dataclass(frozen=True, slots=True)
class AngleReadout:
    """One angle worth calling out - how far a road deviates from continuing
    straight, at a specific point.

    That single framing covers both places it comes up: a new road merging
    into an existing one (0 = merges smoothly, 90 = a perpendicular T), and a
    corner in a road still being drawn (0 = no turn at all). A preview can
    carry more than one - a start connection, an end connection and every
    corner in between are each their own readout at their own position.
    """

    position: Vec2
    degrees: float


@dataclass
class ToolPreview:
    """A tool's work in progress, as geometry rather than as drawing calls."""

    paths: list[Path] = field(default_factory=list)
    points: list[Vec2] = field(default_factory=list)
    """Committed control points, drawn as handles."""
    rubber_band: tuple[Vec2, Vec2] | None = None
    snap: Snap | None = None
    invalid: bool = False
    """The preview cannot be committed as it stands - drawn as a warning."""
    reason: str = ""
    """Why, when `invalid` - carried as data so the overlay can show it, rather
    than a tool reaching past its preview to draw text of its own."""
    measurement: float | None = None
    angles: list[AngleReadout] = field(default_factory=list)
    guides: list[Guide] = field(default_factory=list)
    profile: RoadProfile | None = None
    """Cross-section to use when drawing the preview roads."""

    @property
    def is_empty(self) -> bool:
        return not (
            self.paths
            or self.points
            or self.rubber_band
            or self.snap
            or self.measurement is not None
            or self.angles
            or self.guides
        )


class EditorContext:
    """The editor's shared state. Owned by the scene, handed to every tool."""

    def __init__(self, network: RoadNetwork, camera: Camera) -> None:
        self.network = network
        self.camera = camera
        self.history = History(network)
        self.snapper = Snapper(network, camera)
        self.selection: Selection = EMPTY
        self.cursor: Vec2 = Vec2(0.0, 0.0)
        self.status: str = ""

        self.profile_names: list[str] = sorted(PROFILES)
        self.profile_index: int = self.profile_names.index(DEFAULT_PROFILE.name)

    # -- mutation ----------------------------------------------------------

    def apply(self, command: Command) -> Command:
        """The only way a tool changes anything."""
        self.history.push(command)
        self.status = command.label
        return command

    def undo(self) -> None:
        command = self.history.undo()
        self.status = f"undo {command.label}" if command else "nothing to undo"
        self._forget_missing()

    def redo(self) -> None:
        command = self.history.redo()
        self.status = f"redo {command.label}" if command else "nothing to redo"
        self._forget_missing()

    def replace_network(self, network: RoadNetwork) -> None:
        """Swap in a loaded network. The old undo stack refers to ids that may
        not exist any more, so it goes."""
        self.network = network
        self.history = History(network)
        self.snapper = Snapper(network, self.camera)
        self.selection = EMPTY

    # -- selection ---------------------------------------------------------

    def select(self, selection: Selection) -> None:
        self.selection = selection

    def clear_selection(self) -> None:
        self.selection = EMPTY

    def _forget_missing(self) -> None:
        """Undo can delete what is selected. Selection must not outlive it."""
        sel = self.selection
        if sel.node is not None and sel.node not in self.network.nodes:
            self.selection = EMPTY
        elif sel.segment is not None and sel.segment not in self.network.segments:
            self.selection = EMPTY

    # -- the active profile ------------------------------------------------

    @property
    def profile(self) -> RoadProfile:
        return PROFILES[self.profile_names[self.profile_index]]

    def cycle_profile(self, step: int = 1) -> RoadProfile:
        self.profile_index = (self.profile_index + step) % len(self.profile_names)
        self.status = f"profile: {self.profile.name}"
        return self.profile

    def select_profile(self, name: str) -> RoadProfile:
        """Pick a profile by name - what a road button on the bar does.

        Unknown names are ignored rather than raising: the interface is generated
        from the same registry, so a name that is not there means the two have
        fallen out of step, and taking the window down is not the way to say so.
        """
        if name in self.profile_names:
            self.profile_index = self.profile_names.index(name)
            self.status = f"profile: {name}"
        return self.profile

    # -- convenience for tools --------------------------------------------

    def world(self, screen_x: float, screen_y: float) -> Vec2:
        return self.camera.to_world(screen_x, screen_y)

    def snap(self, point: Vec2, **kwargs) -> Snap:
        return self.snapper.snap(point, **kwargs)
