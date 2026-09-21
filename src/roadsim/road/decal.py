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


def _build() -> dict[str, Decal]:
    return {
        name: Decal(
            name,
            tuple(tuple(Vec2(x, y) for x, y in ring) for ring in rings),
            ASPECT[name],
        )
        for name, rings in RINGS.items()
    }


DECALS: dict[str, Decal] = _build()
"""Every painted marking the game knows, by name."""


def get(name: str) -> Decal:
    try:
        return DECALS[name]
    except KeyError:
        raise KeyError(f"unknown decal {name!r}; have {sorted(DECALS)}") from None
