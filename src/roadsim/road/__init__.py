"""The road model: topology, cross-sections and derived junction geometry.

Knows about `geometry`, and about nothing above it. No pygame in this package -
colors and drawing live in `render/`, tools and undo in `editor/`.
"""

from .anchor import Anchor, end_anchors, node_anchors
from .cap import Cap, CapKind, build_cap
from .crosswalk import CrosswalkMark, crosswalk_mark
from .junction import Junction, SegmentEnd, build_junction
from .lane import Direction, LaneSpec, LaneType
from .markings import LaneMarking, MarkingKind, lane_markings
from .network import RoadNetwork
from .node import RoadNode
from .pavement import PavementBand, build_pavement_bands
from .presets import DEFAULT_PROFILE, PROFILES
from .profile import RoadProfile
from .segment import RoadSegment
from .turn_arrows import TurnArrow, TurnKind, turn_arrows

__all__ = [
    "DEFAULT_PROFILE",
    "PROFILES",
    "Anchor",
    "Cap",
    "CapKind",
    "CrosswalkMark",
    "Direction",
    "Junction",
    "LaneMarking",
    "LaneSpec",
    "LaneType",
    "MarkingKind",
    "PavementBand",
    "RoadNetwork",
    "RoadNode",
    "RoadProfile",
    "RoadSegment",
    "SegmentEnd",
    "TurnArrow",
    "TurnKind",
    "build_cap",
    "build_junction",
    "build_pavement_bands",
    "crosswalk_mark",
    "end_anchors",
    "lane_markings",
    "node_anchors",
    "turn_arrows",
]
