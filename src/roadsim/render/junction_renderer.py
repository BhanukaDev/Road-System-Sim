"""Draws one junction: its blended surface, and any pavement bands its corners
carry.

Extracted from `network_renderer.py` once a junction grew corners and
pavements - a plain polygon fill was the whole of it before M3. A renderer
never mutates the model (D8); this one turns `Junction`/`PavementBand` data
into pygame calls and nothing else.
"""

from __future__ import annotations

import pygame

from .. import config
from ..geometry import Vec2
from ..road.junction import Junction
from ..road.pavement import PavementBand
from .camera import Camera
from .curves import to_screen_points


def draw_junction(surface: pygame.Surface, camera: Camera, junction: Junction) -> None:
    outline = _rounded_outline(junction, camera.world_tolerance)
    if len(outline) < 3:
        return
    points = to_screen_points(camera, outline)
    if junction.is_degenerate:
        # No honest surface here - the mouths overlap, or the ring crosses
        # itself. Filling it anyway is what made a shallow-Y merge look like a
        # rendering glitch instead of geometry that could not be solved, so it
        # is outlined loudly and left unfilled (the same call `is_broken`
        # segments get in `network_renderer`).
        pygame.draw.lines(surface, config.Color.SEGMENT_ERROR, True, points, 2)
        return
    # Two arms meeting is not a crossing - it is one road changing cross-section
    # or heading, and the patch between the mouths is carriageway like the rest
    # of it. Filling it as a junction is what made a kink read as a grey wedge
    # laid over the road rather than part of it.
    crossing = junction.is_crossing
    fill = config.Color.JUNCTION_FILL if crossing else config.Color.JOINT_FILL
    pygame.draw.polygon(surface, fill, points)


def draw_pavement_band(
    surface: pygame.Surface, camera: Camera, band: PavementBand
) -> None:
    tolerance = camera.world_tolerance
    curb = [] if band.curb is None else band.curb.points(tolerance)
    inner = [] if band.inner is None else band.inner.points(tolerance)
    outline = [
        band.outer_start,
        *curb,
        band.outer_end,
        band.inner_end,
        *reversed(inner),
        band.inner_start,
    ]
    points = to_screen_points(camera, outline)
    if len(points) < 3:
        return
    pygame.draw.polygon(surface, config.Color.LANE_SIDEWALK, points)


def _rounded_outline(junction: Junction, tolerance: float) -> list[Vec2]:
    """Walk the mouths counter-clockwise, running each corner's blend between
    them instead of cutting straight across.

    `junction.polygon` already holds two points per end - `(right, left)` at
    that end's own trimmed mouth (`build_junction._mouths`) - and
    `junction.blends[i]` is the kerb from end `i`'s second corner to end
    `i + 1`'s first: exactly the two points either side of the cut it replaces.
    The blend meets both mouths along their own roads' headings, so the fill
    leaves the carriageway without a kink and bows the way the two orientations
    ask it to - which is what turns a triangular gore into a nose.

    A corner with no blend (two mouths on top of each other, nothing to build)
    keeps its straight cut.
    """
    n = len(junction.ends)
    if len(junction.polygon) != 2 * n:
        return list(junction.polygon)
    outline: list[Vec2] = []
    for i in range(n):
        outline.append(junction.polygon[2 * i])
        outline.append(junction.polygon[2 * i + 1])
        blend = junction.blends[i] if i < len(junction.blends) else None
        if blend is not None:
            # Ends trimmed: they *are* the two mouth corners either side, and a
            # fill with a doubled vertex is one more chance to get an edge case
            # wrong for no gain.
            outline.extend(blend.points(tolerance)[1:-1])
    return outline
