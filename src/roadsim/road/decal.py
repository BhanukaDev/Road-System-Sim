"""Painted road decals - arrows, hatching - as polygon rings in world space.

A decal is real geometry, not a sprite. `tools/import_markings.py` converts the
TPDM SVGs once, offline, into `decal_library.py`; nothing here parses SVG and
nothing at runtime rasterises one. That buys three things the hand-built
triangles it replaces could not: the shape is the standard's own, it stays
exact at any zoom instead of resampling, and it ports to a 3D engine as a mesh.

Rings arrive normalised - centred on the origin, +y along the direction of
travel, exactly 1.0 long - so the size lives in `config.py` with every other
tunable (rule 4) rather than in generated data.

A new decal is one line in `DECALS`, which is `CURATED` in the importer
reaching the game (rule 2). No renderer learns its name.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..geometry import Vec2
from .decal_library import ASPECT, RINGS


@dataclass(frozen=True, slots=True)
class Decal:
    name: str
    rings: tuple[tuple[Vec2, ...], ...]
    """One or more closed rings, in the normalised frame. Several rings are
    several separate painted shapes - hatching, or an arrow whose head is not
    joined to its shaft - never a ring and a hole: nothing in the library needs
    one, and a filled hole would be a silent wrong answer rather than a
    visible one."""
    aspect: float
    """Width as a fraction of length. A decal is scaled uniformly, so this is
    what says whether it will fit the lane it is painted in."""

    def fitted_length(self, want: float, max_width: float) -> float:
        """`want` metres long, shortened if that would overflow the lane.

        Scaling is uniform - squashing an arrow to fit a bus lane would make it
        a different marking - so a narrow lane gets a smaller arrow, not a
        thinner one.
        """
        if self.aspect <= 0.0:
            return want
        return min(want, max_width / self.aspect)

    def placed(self, position: Vec2, forward: Vec2, length: float) -> list[list[Vec2]]:
        """The rings in world space, centred at `position`, pointing `forward`.

        `normal = tangent.rot90()` points left (D3), so the decal's own +x -
        the driver's right - is the negated normal.
        """
        right = -forward.rot90()
        return [
            [position + right * (p.x * length) + forward * (p.y * length) for p in ring]
            for ring in self.rings
        ]


def _u_turn_rings() -> tuple[tuple[Vec2, ...], ...]:
    """A U-turn arrow, drawn rather than imported: the TPDM set has none.

    A shaft up the driver's right, a half turn over the top to the left, and
    a head pointing back the way the driver came. Built in an arbitrary size
    and then normalised to the same frame as the library rings - centred,
    +y along travel, exactly 1.0 long - so `placed` treats it like any other.
    """
    import math

    half_gap, thickness = 0.19, 0.12
    outer, inner = half_gap + thickness, half_gap
    top = 0.1
    ring: list[Vec2] = [Vec2(outer, -0.5), Vec2(outer, top)]
    steps = 12
    for i in range(1, steps):
        angle = math.pi * i / steps
        ring.append(Vec2(outer * math.cos(angle), top + outer * math.sin(angle)))
    ring += [
        Vec2(-outer, top),
        Vec2(-outer, -0.2),
        Vec2(-outer - 0.13, -0.2),
        Vec2(-half_gap - thickness / 2.0, -0.5),
        Vec2(-inner + 0.13, -0.2),
        Vec2(-inner, -0.2),
        Vec2(-inner, top),
    ]
    for i in range(steps - 1, 0, -1):
        angle = math.pi * i / steps
        ring.append(Vec2(inner * math.cos(angle), top + inner * math.sin(angle)))
    ring += [Vec2(inner, top), Vec2(inner, -0.5)]

    lo = min(p.y for p in ring)
    hi = max(p.y for p in ring)
    left = min(p.x for p in ring)
    right = max(p.x for p in ring)
    scale = 1.0 / (hi - lo)
    mid_y = (hi + lo) / 2.0
    mid_x = (left + right) / 2.0
    return (tuple(Vec2((p.x - mid_x) * scale, (p.y - mid_y) * scale) for p in ring),)


SYNTHESISED = {"arrow_u_turn": _u_turn_rings}
"""Decals built from geometry rather than imported (D27). One line here is
one new decal, the same as one line in `RINGS`."""


def _build() -> dict[str, Decal]:
    decals = {
        name: Decal(
            name,
            tuple(tuple(Vec2(x, y) for x, y in ring) for ring in rings),
            ASPECT[name],
        )
        for name, rings in RINGS.items()
    }
    for name, make in SYNTHESISED.items():
        rings = make()
        xs = [p.x for ring in rings for p in ring]
        decals[name] = Decal(name, rings, max(xs) - min(xs))
    for mirrored_name, source_name in MIRRORED.items():
        source = decals[source_name]
        decals[mirrored_name] = Decal(
            mirrored_name,
            tuple(tuple(Vec2(-p.x, p.y) for p in ring) for ring in source.rings),
            source.aspect,
        )
    return decals


MIRRORED: dict[str, str] = {
    "arrow_merge_left": "arrow_merge_right",
    "gore_hatch_mirrored": "gore_hatch",
}
"""Decal -> its source, built by negating `x` (the driver's right/left axis).

`arrow_merge_left` (RM_1019) is a plain left-right mirror of `arrow_merge_right`
(RM_1021) - the source library carries no name, but rendering both side by side
confirms it - so only the source's rings are curated and this one is derived,
rather than shipping a second near-duplicate polygon to maintain.

`gore_hatch_mirrored` is for a median taper (`road/median_taper.py`), which
paints the same gore either side of one centreline - `gore_hatch` itself is
not symmetric about its own `x = 0`, so using it unmirrored on both sides
would paint one side's hatching backwards relative to the other."""


DECALS: dict[str, Decal] = _build()
"""Every painted marking the game knows, by name."""


def get(name: str) -> Decal:
    try:
        return DECALS[name]
    except KeyError:
        raise KeyError(f"unknown decal {name!r}; have {sorted(DECALS)}") from None
