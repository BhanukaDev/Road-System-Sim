"""Shared fixtures and tolerances.

These tests are about *exactness*. The whole reason this project uses arcs and
lines rather than splines is that offsetting is closed-form, so the assertions
here are at machine precision, not at "looks about right".
"""

from __future__ import annotations

import math

import pytest

from roadsim.geometry import Path, Vec2, fit_polyline

EXACT = 1e-9
"""Anything that should be closed-form must land inside this."""


def approx(value: float, expected: float, tol: float = EXACT) -> bool:
    return abs(value - expected) <= tol


def assert_vec(a: Vec2, b: Vec2, tol: float = EXACT) -> None:
    assert a.distance_to(b) <= tol, f"{a} != {b}"


@pytest.fixture
def demo_path() -> Path:
    """A path with both left and right turns, and straights of varying length."""
    return fit_polyline(
        [
            Vec2(-90.0, -30.0),
            Vec2(-40.0, -30.0),
            Vec2(-10.0, 20.0),
            Vec2(30.0, 25.0),
            Vec2(45.0, -20.0),
            Vec2(95.0, -25.0),
        ],
        12.0,
    )


@pytest.fixture
def wiggle_path() -> Path:
    """A dense sine sketch, standing in for a freehand stroke."""
    pts = [Vec2(t, 25.0 * math.sin(t / 18.0)) for t in range(0, 170, 3)]
    return fit_polyline(pts, 12.0)
