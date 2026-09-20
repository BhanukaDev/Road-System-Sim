"""Vec2 basics, and the handedness convention everything else depends on."""

from __future__ import annotations

import math

import pytest

from roadsim.geometry import Vec2

from .conftest import EXACT, assert_vec


def test_rot90_turns_counter_clockwise():
    assert_vec(Vec2(1.0, 0.0).rot90(), Vec2(0.0, 1.0))
    assert_vec(Vec2(0.0, 1.0).rot90(), Vec2(-1.0, 0.0))


def test_cross_is_positive_when_other_is_to_the_left():
    """The sign convention that decides which way a corner fillets."""
    assert Vec2(1.0, 0.0).cross(Vec2(0.0, 1.0)) > 0.0
    assert Vec2(1.0, 0.0).cross(Vec2(0.0, -1.0)) < 0.0


def test_normalized_of_zero_is_safe():
    """Degenerate input must not raise - editor input hits this constantly."""
    assert abs(Vec2(0.0, 0.0).normalized().length - 1.0) <= EXACT


@pytest.mark.parametrize("angle", [0.0, 0.7, math.pi / 2, math.pi, -2.4])
def test_from_angle_round_trips(angle):
    assert abs(Vec2.from_angle(angle).angle - angle) <= EXACT


def test_rotated_preserves_length():
    v = Vec2(3.0, -4.0)
    assert abs(v.rotated(1.1).length - 5.0) <= EXACT


def test_is_immutable():
    with pytest.raises(Exception):
        Vec2(1.0, 2.0).x = 5.0  # type: ignore[misc]
