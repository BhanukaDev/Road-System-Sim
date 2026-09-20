"""Turning a centreline plus two lateral offsets into drawable geometry.

A `Ribbon` is a strip of cross-sections taken along a `Path`. Every lane, every
marking and eventually the textured road surface is a ribbon - the only thing
that changes is which offsets you ask for.

Each cross-section carries its arc length `s`, which is the texture V coordinate
when this becomes a textured quad strip, and the ruler for dashed markings.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import cached_property

from .arc import ArcSegment
from .path import Path
from .vec import Vec2


@dataclass(frozen=True, slots=True)
class CrossSection:
    s: float
    center: Vec2
    left: Vec2
    right: Vec2


@dataclass(frozen=True)
class Ribbon:
    sections: tuple[CrossSection, ...]
    left_offset: float
    right_offset: float

    @cached_property
    def length(self) -> float:
        return self.sections[-1].s if self.sections else 0.0

    @property
    def width(self) -> float:
        return abs(self.left_offset - self.right_offset)

    @cached_property
    def outline(self) -> list[Vec2]:
        """Closed polygon: down the left edge, back up the right."""
        return [s.left for s in self.sections] + [
            s.right for s in reversed(self.sections)
        ]

    def quads(self) -> list[tuple[Vec2, Vec2, Vec2, Vec2]]:
        """Consecutive cross-sections as quads, ready for texturing in M3."""
        return [
            (a.left, b.left, b.right, a.right)
            for a, b in zip(self.sections, self.sections[1:])
        ]


def build_ribbon(
    path: Path,
    left_offset: float,
    right_offset: float,
    tolerance: float,
    s0: float | None = None,
    s1: float | None = None,
) -> Ribbon:
    """Sample `path` and displace along its normal to both offsets.

    Displacing the centre frame is exactly equivalent to `path.offset(d)` - the
    cross-sections are radial on arcs - but it keeps the two edges sharing one
    `s`, which is what makes them join into quads.
    """
    lo = 0.0 if s0 is None else path.clamp_s(s0)
    hi = path.length if s1 is None else path.clamp_s(s1)
    half_width = max(abs(left_offset), abs(right_offset))

    sections = []
    for s in _sample_positions(path, tolerance, half_width):
        if s < lo - 1e-9 or s > hi + 1e-9:
            continue
        sections.append(_section_at(path, s, left_offset, right_offset))
    # Guarantee the trimmed ends are represented exactly.
    if not sections or sections[0].s > lo + 1e-9:
        sections.insert(0, _section_at(path, lo, left_offset, right_offset))
    if sections[-1].s < hi - 1e-9:
        sections.append(_section_at(path, hi, left_offset, right_offset))
    return Ribbon(tuple(sections), left_offset, right_offset)


def _section_at(path: Path, s: float, left: float, right: float) -> CrossSection:
    frame = path.sample(s)
    normal = frame.normal
    return CrossSection(
        s, frame.position, frame.position + normal * left, frame.position + normal * right
    )


def _sample_positions(path: Path, tolerance: float, half_width: float) -> list[float]:
    """Flatten, tightening the step on arcs so the *outer* edge stays smooth.

    An edge `w` outside an arc of radius `r` bulges by `(r + w) / r` more than the
    centreline does, so without this the widest lane of a tight curve visibly
    facets while the centreline looks fine.
    """
    out: list[float] = []
    for piece, start in zip(path.pieces, path.piece_starts):
        piece_tol = tolerance
        if isinstance(piece, ArcSegment) and half_width > 0.0:
            piece_tol = tolerance * piece.radius / (piece.radius + half_width)
        for local in piece.flatten(piece_tol):
            s = start + local
            if not out or s - out[-1] > 1e-9:
                out.append(s)
    return out
