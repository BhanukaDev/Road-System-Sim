"""Pure geometry kernel. Knows nothing about roads, pygame or the editor."""

from .arc import ArcSegment
from .curve import Curve, DegenerateOffsetError, Sample
from .fitting import fit_freehand, fit_polyline, simplify
from .line import LineSegment
from .path import Path
from .ribbon import CrossSection, Ribbon, build_ribbon
from .vec import Vec2

__all__ = [
    "ArcSegment",
    "CrossSection",
    "Curve",
    "DegenerateOffsetError",
    "LineSegment",
    "Path",
    "Ribbon",
    "Sample",
    "Vec2",
    "build_ribbon",
    "fit_freehand",
    "fit_polyline",
    "simplify",
]
