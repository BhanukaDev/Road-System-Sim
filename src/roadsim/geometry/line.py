"""Straight tangent piece."""

from __future__ import annotations

from dataclasses import dataclass
from functools import cached_property

from .curve import Curve, Sample
from .vec import Vec2


@dataclass(frozen=True)
class LineSegment(Curve):
    p0: Vec2
    p1: Vec2

    @cached_property
    def direction(self) -> Vec2:
        return (self.p1 - self.p0).normalized()

    @cached_property
    def length(self) -> float:
        return self.p0.distance_to(self.p1)

    def sample(self, s: float) -> Sample:
        s = self.clamp_s(s)
        return Sample(s, self.p0 + self.direction * s, self.direction, 0.0)

    def offset(self, d: float) -> LineSegment:
        shift = self.direction.rot90() * d
        return LineSegment(self.p0 + shift, self.p1 + shift)

    def reversed(self) -> LineSegment:
        return LineSegment(self.p1, self.p0)

    def trimmed(self, s0: float, s1: float) -> LineSegment:
        return LineSegment(self.sample(s0).position, self.sample(s1).position)

    def project(self, point: Vec2) -> float:
        return self.clamp_s((point - self.p0).dot(self.direction))

    def flatten(self, tolerance: float) -> list[float]:
        return [0.0, self.length]
