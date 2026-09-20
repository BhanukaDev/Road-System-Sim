"""Circular arc piece.

Parameterised by centre, radius and a *signed* sweep: positive sweeps
counter-clockwise (a left turn), negative clockwise (a right turn).

The reason this whole project uses arcs rather than splines lives in `offset`:
offsetting an arc is exactly another arc with radius `R - d * sign`. No
resampling, no drift, no self-intersecting polyline offsets.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from functools import cached_property

from .curve import Curve, DegenerateOffsetError, Sample, sagitta_step
from .vec import Vec2


@dataclass(frozen=True)
class ArcSegment(Curve):
    center: Vec2
    radius: float
    start_angle: float
    """Angle of the start point as seen from the centre."""
    sweep: float
    """Signed angle travelled. Positive = counter-clockwise = left turn."""

    def __post_init__(self) -> None:
        if self.radius <= 1e-9:
            raise ValueError(f"arc radius must be positive, got {self.radius}")

    @property
    def turn_sign(self) -> float:
        return 1.0 if self.sweep >= 0.0 else -1.0

    @cached_property
    def length(self) -> float:
        return self.radius * abs(self.sweep)

    def angle_at(self, s: float) -> float:
        return self.start_angle + self.turn_sign * (self.clamp_s(s) / self.radius)

    def sample(self, s: float) -> Sample:
        s = self.clamp_s(s)
        theta = self.angle_at(s)
        radial = Vec2.from_angle(theta)
        # d/dtheta of the radial direction, flipped for a clockwise sweep.
        tangent = Vec2(-radial.y, radial.x) * self.turn_sign
        return Sample(
            s,
            self.center + radial * self.radius,
            tangent,
            self.turn_sign / self.radius,
        )

    def offset(self, d: float) -> ArcSegment:
        # normal = tangent.rot90() = -turn_sign * radial, so a point offset by d
        # sits at radius (R - d * turn_sign) on the same centre.
        new_radius = self.radius - d * self.turn_sign
        if new_radius <= 1e-9:
            raise DegenerateOffsetError(
                f"offset {d} collapses an arc of radius {self.radius}"
            )
        return ArcSegment(self.center, new_radius, self.start_angle, self.sweep)

    def reversed(self) -> ArcSegment:
        return ArcSegment(
            self.center,
            self.radius,
            self.start_angle + self.sweep,
            -self.sweep,
        )

    def trimmed(self, s0: float, s1: float) -> ArcSegment:
        s0, s1 = self.clamp_s(s0), self.clamp_s(s1)
        return ArcSegment(
            self.center,
            self.radius,
            self.angle_at(s0),
            self.turn_sign * (s1 - s0) / self.radius,
        )

    def flatten(self, tolerance: float) -> list[float]:
        step = sagitta_step(self.radius, tolerance)
        count = max(1, math.ceil(abs(self.sweep) / step))
        return [self.length * i / count for i in range(count + 1)]

    def project(self, point: Vec2) -> float:
        delta = (point - self.center).angle - self.start_angle
        # Wrap into the sweep's own direction so `s` comes out non-negative.
        travelled = (delta * self.turn_sign) % (2.0 * math.pi)
        s = travelled * self.radius
        if s <= self.length:
            return s
        # Off the end: snap to whichever endpoint the gap is closer to.
        gap = self.radius * (2.0 * math.pi) - s
        return 0.0 if gap < (s - self.length) else self.length

    # -- construction ------------------------------------------------------

    @staticmethod
    def from_tangent_points(
        entry: Vec2, entry_dir: Vec2, exit_point: Vec2, radius: float
    ) -> ArcSegment:
        """Arc leaving `entry` along `entry_dir` and arriving at `exit_point`."""
        to_exit = exit_point - entry
        sign = 1.0 if entry_dir.cross(to_exit) >= 0.0 else -1.0
        center = entry + entry_dir.rot90() * (radius * sign)
        start_angle = (entry - center).angle
        end_angle = (exit_point - center).angle
        sweep = (end_angle - start_angle) % (2.0 * math.pi)
        if sign < 0.0:
            sweep -= 2.0 * math.pi
        return ArcSegment(center, radius, start_angle, sweep)
