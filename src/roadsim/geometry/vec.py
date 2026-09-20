"""Immutable 2D vector.

World space is standard maths orientation: +x right, +y *up*. The camera is the
only place that flips y for the screen. Keeping the world right-handed means the
left/right handedness of lane offsets is consistent everywhere else.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Vec2:
    x: float = 0.0
    y: float = 0.0

    def __add__(self, o: Vec2) -> Vec2:
        return Vec2(self.x + o.x, self.y + o.y)

    def __sub__(self, o: Vec2) -> Vec2:
        return Vec2(self.x - o.x, self.y - o.y)

    def __mul__(self, k: float) -> Vec2:
        return Vec2(self.x * k, self.y * k)

    __rmul__ = __mul__

    def __truediv__(self, k: float) -> Vec2:
        return Vec2(self.x / k, self.y / k)

    def __neg__(self) -> Vec2:
        return Vec2(-self.x, -self.y)

    def __iter__(self):
        yield self.x
        yield self.y

    @property
    def length(self) -> float:
        return math.hypot(self.x, self.y)

    @property
    def length_sq(self) -> float:
        return self.x * self.x + self.y * self.y

    def normalized(self) -> Vec2:
        n = self.length
        if n < 1e-12:
            return Vec2(1.0, 0.0)
        return Vec2(self.x / n, self.y / n)

    def dot(self, o: Vec2) -> float:
        return self.x * o.x + self.y * o.y

    def cross(self, o: Vec2) -> float:
        """z-component of the 3D cross product. >0 when `o` is left of `self`."""
        return self.x * o.y - self.y * o.x

    def rot90(self) -> Vec2:
        """Rotate 90 degrees counter-clockwise. This is the left-hand normal."""
        return Vec2(-self.y, self.x)

    def rotated(self, radians: float) -> Vec2:
        c, s = math.cos(radians), math.sin(radians)
        return Vec2(self.x * c - self.y * s, self.x * s + self.y * c)

    @property
    def angle(self) -> float:
        return math.atan2(self.y, self.x)

    @staticmethod
    def from_angle(radians: float, length: float = 1.0) -> Vec2:
        return Vec2(math.cos(radians) * length, math.sin(radians) * length)

    def distance_to(self, o: Vec2) -> float:
        return math.hypot(self.x - o.x, self.y - o.y)


ZERO = Vec2(0.0, 0.0)
