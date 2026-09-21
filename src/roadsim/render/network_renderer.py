"""Draws a `RoadNetwork`. Read-only: a renderer never mutates the model.

Order matters and is fixed here: lane ribbons bottom-up by layer, then lane
markings on top of them, then junction surfaces filling the gaps the trims
opened, then crosswalks and stop lines at real junctions, then direction
arrows on top of that. Lane colours are not decided here - `lane_style.py`
owns that mapping, so a new lane type never touches this file.

Every ribbon is built at `camera.world_tolerance`, so the geometry gets finer as
you zoom in and cheaper as you zoom out (D7).
"""

from __future__ import annotations

import pygame

from .. import config
from ..geometry import Vec2
from ..road import RoadNetwork, RoadSegment
from ..road.cap import Cap, CapKind
from ..road.crosswalk import CrosswalkMark, crosswalk_mark
from ..road.decal import get as decal_for
from ..road.junction import Junction
from ..road.lane import Direction, LaneType
from ..road.median_taper import MedianTaper, median_tapers
from ..road.pavement import build_pavement_bands
from ..road.transition import build_transition
from ..road.turn_arrows import arrows_for_mouth
from .camera import Camera
from .crosswalk_renderer import draw_crosswalk
from .curves import to_screen_points
from .decal_renderer import draw_decal
from .junction_renderer import draw_junction, draw_pavement_band
from .lane_markings import draw_markings
from .lane_style import LAYERS, style_for
from .median_taper_renderer import draw_median_taper
from .transition_renderer import draw_transition


class NetworkRenderer:
    def __init__(self, show_arrows: bool = True) -> None:
        self.show_arrows = show_arrows
        """Periodic travel-direction chevrons only - an editing aid, not paint.
        Turn-arrow decals at a junction mouth are real road markings and always
        draw, the same as a crosswalk."""

    def draw(
        self,
        surface: pygame.Surface,
        camera: Camera,
        network: RoadNetwork,
        segment_ids: frozenset[int] | None = None,
        node_ids: frozenset[int] | None = None,
    ) -> None:
        """Draw the network, or just the part of it named.

        `segment_ids` and `node_ids` scope the pass to a subset - the roads a
        ghost preview created or re-trimmed and the nodes whose junction or cap
        it rebuilt (`editor/ghost.py`). `None` for either means all of them.
        Everything a subset junction needs - the arms it trims, the bands it
        runs - is still read from the whole network, so a partial draw is the
        full draw with fewer things painted, never a different drawing.
        """
        segments = [
            s
            for s in network.segments.values()
            if segment_ids is None or s.id in segment_ids
        ]
        junctions = [
            j
            for j in network.junctions.values()
            if node_ids is None or j.node_id in node_ids
        ]
        caps = [
            c
            for c in network.caps.values()
            if node_ids is None or c.node_id in node_ids
        ]
        drawable = [s for s in segments if not s.is_broken]
        tapers = {
            segment.id: median_tapers(
                segment,
                network.junctions.get(segment.node_a),
                network.junctions.get(segment.node_b),
            )
            for segment in drawable
        }

        for layer in LAYERS:
            for segment in drawable:
                self._draw_lanes(surface, camera, segment, layer, tapers[segment.id])

        for segment in drawable:
            draw_markings(
                surface,
                camera,
                segment.path,
                segment.profile,
                segment.trim_a,
                segment.path.length - segment.trim_b,
                _median_marking_overrides(segment, tapers[segment.id]),
            )
            for taper in tapers[segment.id]:
                draw_median_taper(surface, camera, taper)

        for junction in junctions:
            draw_junction(surface, camera, junction)
            if junction.is_degenerate:
                # Nothing derived from these mouths is trustworthy - a pavement
                # band would be stretched across both carriageways, and a stop
                # line would sit where the kerbs have not separated yet.
                continue
            ends = network.segments_at(junction.node_id)
            seg_by_key = {(seg.id, at_a): seg for seg, at_a in ends}
            for band in build_pavement_bands(junction, seg_by_key):
                draw_pavement_band(surface, camera, band)
            transition = build_transition(junction, seg_by_key)
            if transition is not None:
                draw_transition(surface, camera, transition)
            if junction.is_crossing:
                for segment, at_a in ends:
                    if segment.is_broken:
                        continue
                    mark = crosswalk_mark(segment, at_a)
                    if mark is None:
                        continue
                    draw_crosswalk(surface, camera, segment.path, mark)
                    self._draw_turn_arrows(
                        surface, camera, segment, at_a, mark, junction
                    )

        for cap in caps:
            self._draw_cap(surface, camera, cap)

        if self.show_arrows:
            for segment in drawable:
                self._draw_arrows(surface, camera, segment)

        for segment in segments:
            if segment.is_broken:
                self._draw_error(surface, camera, segment)

    # -- pieces ------------------------------------------------------------

    def _draw_lanes(
        self,
        surface: pygame.Surface,
        camera: Camera,
        segment: RoadSegment,
        layer: int,
        tapers: tuple[MedianTaper, ...],
    ) -> None:
        tolerance = camera.world_tolerance
        for k, lane in enumerate(segment.profile.lanes):
            style = style_for(lane.type)
            if style.layer != layer:
                continue
            s0, s1 = segment.trim_a, segment.path.length - segment.trim_b
            if lane.type is LaneType.MEDIAN:
                # A taper replaces the constant-width ribbon for the last
                # stretch before its mouth with the narrowing island
                # `draw_median_taper` paints instead, so the plain ribbon must
                # stop where that island starts rather than running under it.
                for taper in tapers:
                    if taper.lane_index != k:
                        continue
                    if taper.at_a:
                        s0 = max(s0, taper.full_s)
                    else:
                        s1 = min(s1, taper.full_s)
            outline = to_screen_points(
                camera, segment.lane_ribbon(k, tolerance, s0, s1).outline
            )
            if len(outline) < 3:
                continue
            pygame.draw.polygon(surface, style.fill, outline)

    def _draw_cap(self, surface: pygame.Surface, camera: Camera, cap: Cap) -> None:
        if cap.kind is CapKind.TERMINAL:
            points = to_screen_points(camera, [cap.left, cap.right])
            pygame.draw.lines(
                surface,
                config.Color.STOP_LINE,
                False,
                points,
                max(1, round(config.STOP_LINE_WIDTH_PX)),
            )
            return
        bulge = cap.bulge
        arc_points = [
            bulge.sample(s).position for s in bulge.flatten(camera.world_tolerance)
        ]
        points = to_screen_points(camera, [cap.left, *arc_points, cap.right])
        if len(points) < 3:
            return
        pygame.draw.polygon(surface, config.Color.CAP_FILL, points)

    def _draw_arrows(
        self, surface: pygame.Surface, camera: Camera, segment: RoadSegment
    ) -> None:
        """Travel-direction chevrons, spaced along the centreline's arc length.

        Spacing comes off the centreline rather than each lane's own offset
        path, which is what keeps the arrows in a multi-lane curve lined up
        across the road instead of drifting apart lane by lane.
        """
        if segment.carriageway_length * camera.zoom < config.DIRECTION_ARROW_MIN_PX:
            return
        profile = segment.profile
        stations = _stations(
            segment.trim_a,
            segment.path.length - segment.trim_b,
            config.DIRECTION_ARROW_SPACING,
        )
        half = config.DIRECTION_ARROW_LENGTH / 2.0
        for k, lane in enumerate(profile.lanes):
            if not lane.type.carries_vehicles or not lane.direction.is_traffic:
                continue
            offset = profile.lane_center(k)
            signs = _arrow_signs(lane.direction)
            # A two-way lane gets its arrows nose to nose rather than stacked on
            # one point, where they would read as a bowtie instead of two arrows.
            spread = half * 1.3 if len(signs) > 1 else 0.0
            for s in stations:
                for sign in signs:
                    frame = segment.path.sample(s + sign * spread)
                    center = frame.position + frame.normal * offset
                    self._draw_arrow(
                        surface, camera, center, frame.tangent * sign, half, lane.width
                    )

    def _draw_arrow(
        self,
        surface: pygame.Surface,
        camera: Camera,
        center: Vec2,
        direction: Vec2,
        half: float,
        lane_width: float,
    ) -> None:
        base = center - direction * half
        self._draw_arrow_branch(
            surface, camera, base, direction, half * 2.0, lane_width
        )

    def _draw_arrow_branch(
        self,
        surface: pygame.Surface,
        camera: Camera,
        base: Vec2,
        direction: Vec2,
        length: float,
        lane_width: float,
    ) -> None:
        wing = min(lane_width * 0.22, length * 0.4)
        tip = base + direction * length
        side = direction.rot90() * wing
        points = to_screen_points(camera, [tip, base + side, base - side])
        pygame.draw.polygon(surface, config.Color.DIRECTION_ARROW, points)

    def _draw_turn_arrows(
        self,
        surface: pygame.Surface,
        camera: Camera,
        segment: RoadSegment,
        at_a: bool,
        mark: CrosswalkMark,
        junction: Junction,
    ) -> None:
        """One decal per approaching lane, upstream of the stop line.

        `arrows_for_mouth` says which lanes and which option; the shape itself
        is the TPDM marking off `road/decal.py`, scaled down where a narrow
        lane cannot hold it at full size.
        """
        away = 1.0 if at_a else -1.0
        s = segment.path.clamp_s(mark.stop_s + away * config.TURN_ARROW_SETBACK)
        frame = segment.path.sample(s)
        profile = segment.profile
        for arrow in arrows_for_mouth(profile, at_a, junction, segment.id):
            decal = decal_for(arrow.kind.decal)
            lane_width = profile.lanes[arrow.lane].width
            length = decal.fitted_length(
                config.TURN_ARROW_LENGTH, lane_width * config.TURN_ARROW_LANE_FRACTION
            )
            draw_decal(
                surface,
                camera,
                decal,
                frame.position + frame.normal * profile.lane_center(arrow.lane),
                frame.tangent * arrow.sign,
                length,
            )

    def _draw_error(
        self, surface: pygame.Surface, camera: Camera, segment: RoadSegment
    ) -> None:
        """A segment that cannot be drawn as a road - eaten by its junctions, or
        curved tighter than its own width allows. Drawn, loudly, as a centreline
        rather than silently skipped: the user needs to see where it went."""
        points = to_screen_points(camera, segment.path.points(camera.world_tolerance))
        if len(points) >= 2:
            pygame.draw.lines(surface, config.Color.SEGMENT_ERROR, False, points, 3)


def _median_marking_overrides(
    segment: RoadSegment, tapers: tuple[MedianTaper, ...]
) -> dict[float, tuple[float, float]] | None:
    """The span each of a tapering median's own edge lines gets, keyed by its
    offset - the same `full_s` cutoff `_draw_lanes` gives that lane's ribbon,
    so the straight line and the narrowing island stop at the same point."""
    if not tapers:
        return None
    default = (segment.trim_a, segment.path.length - segment.trim_b)
    overrides: dict[float, tuple[float, float]] = {}
    for taper in tapers:
        for offset in segment.profile.lane_bounds(taper.lane_index):
            key = round(offset, 9)
            s0, s1 = overrides.get(key, default)
            if taper.at_a:
                s0 = max(s0, taper.full_s)
            else:
                s1 = min(s1, taper.full_s)
            overrides[key] = (s0, s1)
    return overrides


def _arrow_signs(direction: Direction) -> tuple[float, ...]:
    if direction is Direction.FORWARD:
        return (1.0,)
    if direction is Direction.BACKWARD:
        return (-1.0,)
    return (1.0, -1.0)


def _stations(s0: float, s1: float, spacing: float) -> list[float]:
    """Evenly spaced arc lengths, centred in the span so both ends stay clear."""
    span = s1 - s0
    count = int(span // spacing)
    if count < 1:
        return [s0 + span / 2.0] if span > 0.0 else []
    start = s0 + (span - (count - 1) * spacing) / 2.0
    return [start + i * spacing for i in range(count)]
