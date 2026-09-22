"""Where a median lane narrows to a nose approaching a real crossing.

A median that holds its full width right up to a crossing's mouth and then
stops dead reads as a slab shoved against the intersection with no
transition - and the crossing has already eaten the room a full-width median
would need there (D17: the joint patch is one slab of carriageway). This
derives a taper the same way everything else at a junction is (D5): from the
segment and the junction it meets, never stored.

Only a real crossing (`Junction.is_crossing`, 3+ arms) earns one. A dead end,
a straight-through joint (no `Junction` at all - `build_junction` calls that a
joint in one road, D17) and a two-arm profile transition all leave the median
at full width to the mouth, because none of them has actually eaten the
median's room the way a crossing has.

The width the taper gives up on each side is not left as bare asphalt: it is
painted with the same `gore_hatch` decal (`road/decal.py`) a lane-count
transition's gore already uses - a median narrowing to a point *is* a gore,
just a short, symmetric one on both sides of the centreline instead of a
single one-sided wedge.

**The taper has to finish before the crosswalk, not inside it.** A crossing's
zebra stripes (`road/crosswalk.py`) start right at the same mouth and run
`CROSSWALK_DEPTH` further in - the same stretch this module used to spend
tapering. Painted hatching and painted stripes sharing one patch of road drew
as a tangle of white lines fighting each other, not a gore. So the island
narrows to its nose *before* that reserved stretch, then carries on at a
constant, un-hatched nose width as a plain refuge through the stripes - the
same thing a real narrow median does at a crossing.
"""

from __future__ import annotations

from dataclasses import dataclass

from .. import config
from ..geometry import LineSegment, Path, Vec2
from .decal import get as decal_for
from .junction import Junction
from .lane import LaneType
from .segment import RoadSegment

_GORE_HATCH = decal_for("gore_hatch")


@dataclass(frozen=True, slots=True)
class HatchWedge:
    position: Vec2
    forward: Vec2
    length: float
    decal: str


@dataclass(frozen=True, slots=True)
class MedianTaper:
    lane_index: int
    at_a: bool
    full_s: float
    """Arc length where the lane is still at its full width - the far edge of
    the reduced span a renderer draws the constant-width ribbon over."""
    island: tuple[Vec2, Vec2, Vec2, Vec2]
    """The narrowing pavement: full width at `full_s`, down to the nose at
    `taper_end_s`."""
    refuge: tuple[Vec2, Vec2, Vec2, Vec2]
    """The nose, unchanged in width, carried on from `taper_end_s` to the true
    mouth - the stretch a crosswalk's stripes also occupy, so this stays a
    plain island rather than hatching fighting the stripes for the same paint."""
    gores: tuple[tuple[Vec2, ...], tuple[Vec2, ...]]
    """The width the lane gives up on each side, as a plain paved pentagon: a
    point at `full_s`, opening to the full gap by `taper_end_s`, then running
    at that constant gap to the true mouth. `gore_hatch` (`hatches`) is a
    scatter of painted strokes, not a fill, so without a paved base under it -
    and under the un-hatched stretch alongside the refuge - the gaps between
    those strokes and the crosswalk's own stripes showed bare ground instead
    of ordinary road surface."""
    edges: tuple[Path, Path]
    """The median-edge line on each side, converging from the full-width edge
    to the nose over the taper alone - so the paint follows the island instead
    of running straight through where it has narrowed away."""
    hatches: tuple[HatchWedge, HatchWedge]


def median_tapers(
    segment: RoadSegment,
    junction_a: Junction | None,
    junction_b: Junction | None,
) -> tuple[MedianTaper, ...]:
    """One entry per median lane end that meets a real crossing."""
    if segment.is_broken or segment.is_transition:
        return ()  # a taper's median, if any, is already changing width
    out: list[MedianTaper] = []
    for lane_index in segment.profile.of_type(LaneType.MEDIAN):
        lane_width = segment.profile.lanes[lane_index].width
        nose_width = min(config.MEDIAN_NOSE_WIDTH, lane_width)
        half_gap = (lane_width - nose_width) / 2.0
        if half_gap <= 1e-6:
            continue
        for at_a, junction in ((True, junction_a), (False, junction_b)):
            if junction is None or not junction.is_crossing or junction.is_degenerate:
                continue
            taper = _build(segment, lane_index, lane_width, nose_width, half_gap, at_a)
            if taper is not None:
                out.append(taper)
    return tuple(out)


def _build(
    segment: RoadSegment,
    lane_index: int,
    lane_width: float,
    nose_width: float,
    half_gap: float,
    at_a: bool,
) -> MedianTaper | None:
    budget = segment.carriageway_length * config.MEDIAN_TAPER_MAX_FRACTION
    setback = min(config.CROSSWALK_DEPTH, budget * 0.5)
    taper_length = _GORE_HATCH.fitted_length(config.MEDIAN_TAPER_LENGTH, half_gap)
    taper_length = min(taper_length, max(budget - setback, 0.0))
    if taper_length <= 1e-6:
        # No honest room for a lead-in - a nose with no taper reads as a wall,
        # so the median is left at full width rather than stepping down flat.
        return None

    mouth_s = segment.end_s(at_a)
    taper_end_s = mouth_s + setback if at_a else mouth_s - setback
    full_s = taper_end_s + taper_length if at_a else taper_end_s - taper_length
    center = segment.profile.lane_center(lane_index)
    half_full, half_nose = lane_width / 2.0, nose_width / 2.0

    full_frame = segment.path.sample(full_s)
    taper_end_frame = segment.path.sample(taper_end_s)
    mouth_frame = segment.path.sample(mouth_s)

    def point(frame, offset: float) -> Vec2:
        return frame.position + frame.normal * offset

    island = (
        point(full_frame, center + half_full),
        point(taper_end_frame, center + half_nose),
        point(taper_end_frame, center - half_nose),
        point(full_frame, center - half_full),
    )
    refuge = (
        point(taper_end_frame, center + half_nose),
        point(mouth_frame, center + half_nose),
        point(mouth_frame, center - half_nose),
        point(taper_end_frame, center - half_nose),
    )
    gores = tuple(
        (
            point(full_frame, center + sign * half_full),
            point(taper_end_frame, center + sign * half_full),
            point(mouth_frame, center + sign * half_full),
            point(mouth_frame, center + sign * half_nose),
            point(taper_end_frame, center + sign * half_nose),
        )
        for sign in (1.0, -1.0)
    )
    edges = tuple(
        Path.of(
            LineSegment(
                point(full_frame, center + sign * half_full),
                point(taper_end_frame, center + sign * half_nose),
            )
        )
        for sign in (1.0, -1.0)
    )

    forward = segment.outgoing_dir(at_a)
    mid_frame = segment.path.sample((full_s + taper_end_s) / 2.0)
    hatches = tuple(
        HatchWedge(
            point(mid_frame, center + sign * (half_full + half_nose) / 2.0),
            forward,
            taper_length,
            decal,
        )
        for sign, decal in ((1.0, "gore_hatch"), (-1.0, "gore_hatch_mirrored"))
    )

    return MedianTaper(lane_index, at_a, full_s, island, refuge, gores, edges, hatches)
