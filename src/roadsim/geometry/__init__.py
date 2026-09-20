"""Pure geometry kernel. Knows nothing about roads, pygame or the editor."""

from .aabb import Aabb, arc_bounds, curve_bounds, line_bounds, path_bounds
from .arc import ArcSegment
from .curve import Curve, DegenerateOffsetError, Sample
from .fillet import Fillet, corner_fillet, deflection
from .fitting import fit_freehand, fit_polyline, simplify
from .intersect import (
    Hit,
    arc_arc,
    arcs_overlap,
    curve_curve,
    line_arc,
    line_line,
    path_intersections,
    path_self_intersections,
    path_touches,
    ray_ray,
)
from .line import LineSegment
from .path import Path
from .polygon import is_ccw, signed_area
from .ribbon import CrossSection, Ribbon, build_ribbon
from .vec import Vec2

__all__ = [
    "Aabb",
    "ArcSegment",
    "CrossSection",
    "Curve",
    "DegenerateOffsetError",
    "Fillet",
    "Hit",
    "LineSegment",
    "Path",
    "Ribbon",
    "Sample",
    "Vec2",
    "arc_arc",
    "arc_bounds",
    "arcs_overlap",
    "build_ribbon",
    "corner_fillet",
    "curve_bounds",
    "curve_curve",
    "deflection",
    "fit_freehand",
    "fit_polyline",
    "is_ccw",
    "line_arc",
    "line_bounds",
    "line_line",
    "path_bounds",
    "path_intersections",
    "path_self_intersections",
    "path_touches",
    "ray_ray",
    "signed_area",
    "simplify",
]
