"""The one interface every piece of road geometry is built on.

A `Curve` is parameterised by **arc length** `s` in [0, length], never by an
abstract `t`. That is what makes evenly-spaced lane markings, vehicle movement at
a given speed, and texture V coordinates fall out for free.

Handedness: `normal` is `tangent.rot90()`, i.e. it points to the **left** of the
direction of travel. So `offset(+d)` shifts left and `offset(-d)` shifts right.
"""

from __future__ import annotations

import math
from abc import ABC, abstractmethod
from dataclasses import dataclass

from .vec import Vec2


@dataclass(frozen=True, slots=True)
class Sample:
    """A frame on the curve at a given arc length."""

    s: float
    position: Vec2
    tangent: Vec2
    curvature: float
    """Signed: positive turns left (counter-clockwise), 0 for a straight."""

    @property
    def normal(self) -> Vec2:
        return self.tangent.rot90()

    @property
    def heading(self) -> float:
        return self.tangent.angle


class DegenerateOffsetError(ValueError):
    """Raised when an offset would collapse or invert an arc (|d| >= radius)."""


class Curve(ABC):
    """A single line or arc piece. Immutable."""

    @property
    @abstractmethod
    def length(self) -> float: ...

    @abstractmethod
    def sample(self, s: float) -> Sample:
        """Frame at arc length `s`, clamped to the curve."""

    @abstractmethod
    def offset(self, d: float) -> Curve:
        """A parallel curve `d` to the left. Exact - no resampling."""

    @abstractmethod
    def reversed(self) -> Curve: ...

    @abstractmethod
    def trimmed(self, s0: float, s1: float) -> Curve:
        """The sub-curve between two arc lengths."""

    @abstractmethod
    def project(self, point: Vec2) -> float:
        """Arc length of the closest point on the curve. Used for snapping."""

    @abstractmethod
    def flatten(self, tolerance: float) -> list[float]:
        """Arc lengths to sample at so the chord error stays under `tolerance`.

        Always includes 0.0 and `length`. Straights return just the endpoints;
        arcs subdivide by sagitta, so zooming in costs vertices only where
        curvature actually needs them.
        """

    # -- conveniences shared by every implementation -----------------------

    @property
    def start(self) -> Sample:
        return self.sample(0.0)

    @property
    def end(self) -> Sample:
        return self.sample(self.length)

    def points(self, tolerance: float) -> list[Vec2]:
        return [self.sample(s).position for s in self.flatten(tolerance)]

    def clamp_s(self, s: float) -> float:
        return min(max(s, 0.0), self.length)


def sagitta_step(radius: float, tolerance: float) -> float:
    """Max angular step whose chord deviates from the arc by <= `tolerance`."""
    if tolerance <= 0.0 or tolerance >= 2.0 * radius:
        return math.pi / 4.0
    return 2.0 * math.acos(1.0 - tolerance / radius)
