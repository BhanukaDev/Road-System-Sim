"""An ordered chain of curve pieces sharing one global arc-length parameter.

A road centreline is a `Path`. Because every piece offsets exactly and the chain
is tangent-continuous, `path.offset(d)` is itself a valid `Path` - which is the
whole trick behind lane geometry, asymmetric profiles and junction trimming.
"""

from __future__ import annotations

import bisect
from dataclasses import dataclass, field
from functools import cached_property

from .curve import Curve, Sample
from .vec import Vec2


@dataclass(frozen=True)
class Path:
    pieces: tuple[Curve, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not self.pieces:
            raise ValueError("a Path needs at least one piece")

    @classmethod
    def of(cls, *pieces: Curve) -> Path:
        return cls(tuple(pieces))

    @cached_property
    def piece_starts(self) -> list[float]:
        """Arc length at which each piece begins."""
        starts, acc = [], 0.0
        for piece in self.pieces:
            starts.append(acc)
            acc += piece.length
        return starts

    @cached_property
    def length(self) -> float:
        return sum(piece.length for piece in self.pieces)

    def clamp_s(self, s: float) -> float:
        return min(max(s, 0.0), self.length)

    def _locate(self, s: float) -> tuple[int, float]:
        """(piece index, local arc length) for a global arc length."""
        s = self.clamp_s(s)
        i = bisect.bisect_right(self.piece_starts, s) - 1
        i = min(max(i, 0), len(self.pieces) - 1)
        return i, s - self.piece_starts[i]

    def sample(self, s: float) -> Sample:
        i, local = self._locate(s)
        inner = self.pieces[i].sample(local)
        return Sample(self.clamp_s(s), inner.position, inner.tangent, inner.curvature)

    def offset(self, d: float) -> Path:
        return Path(tuple(piece.offset(d) for piece in self.pieces))

    def reversed(self) -> Path:
        return Path(tuple(piece.reversed() for piece in reversed(self.pieces)))

    def trimmed(self, s0: float, s1: float) -> Path:
        """The sub-path between two arc lengths. Drops pieces outside the range."""
        s0, s1 = self.clamp_s(s0), self.clamp_s(s1)
        if s1 - s0 < 1e-9:
            raise ValueError(f"cannot trim Path to zero length ({s0} -> {s1})")
        kept: list[Curve] = []
        for piece, start in zip(self.pieces, self.piece_starts):
            lo, hi = max(s0 - start, 0.0), min(s1 - start, piece.length)
            if hi - lo > 1e-9:
                kept.append(piece.trimmed(lo, hi))
        return Path(tuple(kept))

    def shortened(self, from_start: float = 0.0, from_end: float = 0.0) -> Path:
        """Pull both ends in. This is how junctions carve space out of a road."""
        return self.trimmed(from_start, self.length - from_end)

    def project(self, point: Vec2) -> float:
        """Global arc length of the closest point on the path."""
        best_s, best_d2 = 0.0, float("inf")
        for piece, start in zip(self.pieces, self.piece_starts):
            local = piece.project(point)
            d2 = (piece.sample(local).position - point).length_sq
            if d2 < best_d2:
                best_s, best_d2 = start + local, d2
        return best_s

    def flatten(self, tolerance: float) -> list[float]:
        """Global arc lengths to sample at, with shared joins emitted once."""
        out: list[float] = []
        for piece, start in zip(self.pieces, self.piece_starts):
            for local in piece.flatten(tolerance):
                s = start + local
                if not out or s - out[-1] > 1e-9:
                    out.append(s)
        return out

    def points(self, tolerance: float) -> list[Vec2]:
        return [self.sample(s).position for s in self.flatten(tolerance)]

    @property
    def start(self) -> Sample:
        return self.sample(0.0)

    @property
    def end(self) -> Sample:
        return self.sample(self.length)
