"""The road model: topology, cross-sections and derived junction geometry.

Knows about `geometry`, and about nothing above it. No pygame in this package -
colors and drawing live in `render/`, tools and undo in `editor/`.
"""

from .cap import Cap, CapKind, build_cap
from .junction import Junction, SegmentEnd, build_junction
from .lane import Direction, LaneSpec, LaneType
from .network import RoadNetwork
from .node import RoadNode
from .presets import DEFAULT_PROFILE, PROFILES
from .profile import RoadProfile
from .segment import RoadSegment

__all__ = [
    "DEFAULT_PROFILE",
    "PROFILES",
    "Cap",
    "CapKind",
    "Direction",
    "Junction",
    "LaneSpec",
    "LaneType",
    "RoadNetwork",
    "RoadNode",
    "RoadProfile",
    "RoadSegment",
    "SegmentEnd",
    "build_cap",
    "build_junction",
]
