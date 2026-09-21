# M3 - Editor, UI and crossings

**Goal:** an editor you can actually build a network with, on a model that still
holds when traffic lands. Cities: Skylines 2 is the reference for how it should
feel; the geometry stays this repo's own.

**Prerequisite:** M2 (done). Read `CLAUDE.md` and `docs/decisions.md` first -
D1-D8 constrain most of what follows, and this milestone adds D9-D13.

**Why before traffic:** every item below is a _model or editor_ question. Putting
textures in front of them would mean texturing geometry that is about to change,
and putting vehicles in front would mean driving them over roads that cannot yet
cross each other.

---

## Where M2 actually left things

Things that do not work, in the user's words, turned into the list this milestone
answers:

| #   | What is wrong today                                                                      | Where                               |
| --- | ---------------------------------------------------------------------------------------- | ----------------------------------- |
| 1   | A road drawn back to its own start is **refused** - no loops, so no roundabouts          | `build_road_command`                |
| 2   | The interface "feels more like a terminal app than a game UI"                            | `render/hud.py` was the whole of it |
| 3   | One editor, no modes - no way to look without touching                                   | `scenes/editor.py`                  |
| 4   | No bulldozer, so no way to see what a delete will take before it takes it                | -                                   |
| 5   | One drawing behaviour, not CS2's straight / curve / complex / continuous, and no replace | `tools/draw_road.py`                |
| 6   | A road preview is a one-pixel centreline, not a road                                     | `ToolPreview.paths`                 |
| 7   | A curve gives no construction lines while you place it                                   | -                                   |
| 8   | Dead ends are square - no turning head, no terminal                                      | -                                   |
| 9   | No alignment guides near other roads                                                     | -                                   |
| 10  | No collision detection: extreme shapes and self-overlap both pass                        | -                                   |
| 11  | No live measurements - length, angle, what you are connecting to                         | -                                   |
| 12  | Snapping is centre-only, so different lane counts always centre-align                    | `editor/snapping.py`                |
| 13  | Two roads crossing without a shared node **do not form a junction**                      | nothing detects crossings           |
| 14  | No height, so no bridges or overpasses                                                   | -                                   |
| 15  | Junctions have no pavement and square corners                                            | `road/junction.py`                  |
| 16  | "Panning not working"                                                                    | `app.py`                            |

Plus the two debts `CLAUDE.md` already recorded against M2 - exact curve-curve
junction intersection instead of the straight-ray approximation and its trim cap,
and splitting a road where a new one _crosses_ it. They are not separate errands:
they are the foundation under 10, 13 and 15.

---

## Decisions taken up front

These were settled before any code and shape everything below. Each becomes a
numbered entry in `docs/decisions.md` as it lands.

1. **Loops auto-split into two segments** sharing both endpoints. No segment ever
   closes on itself and `Path` stays an open chain, so `geometry/` learns nothing
   about closure and junction derivation keeps its two-distinct-ends assumption.
2. **Height is an integer `level` on `RoadNode`** (D9). Metres are derived
   (`config.LEVEL_HEIGHT * level`). A segment's height interpolates between its
   end nodes, so a ramp is two nodes at different levels - no new concept. A node
   has exactly one level, so `junctions` stays keyed by node id.
3. **A crossing forms a junction only when both roads' heights match there**
   (within `config.LEVEL_MERGE_M`). A mismatch is an overpass: no node, no
   junction. The game stays 2D; height is data, not a third axis.
4. **Road buttons draw a cross-section swatch** built from the profile's own lanes
   and coloured through `render/lane_style.py` - the only place lane colours live.
5. **Modes are runtime-switchable over one shared `EditorContext`** (D11).
   `--scene debug` and `--scene network` keep working untouched.
6. **Pan is WASD + arrows + screen edge + middle-drag.** Deliberately _not_
   right-drag: that keeps right-click free as a tool action, so no press-versus-drag
   disambiguation is needed anywhere.
7. **A junction corner handle slides along each arm** (D13). Its distance from the
   junction sets _both_ the corner radius and how far that arm is pushed back.
   Stored per segment end (`pull_a` / `pull_b`, `None` meaning derive it) because
   it is user intent - the same reasoning D5 reserves for M4's lane connections.
8. **Every junction corner is rounded, with the radius clamped by the corner
   angle**, so a sharp corner comes out nearly sharp on its own and there is no
   special case for "outside" corners.

---

## Build order

Each step leaves the app runnable and the suite green.

1. ~~**Controls and crash safety.** `render/camera_input.py`; `app.py` delegates;
   `is_degenerate` on segments; the `mirrored()` name fix; magic numbers to
   `config.py`.~~ **done**
2. ~~**`geometry/`: the exact primitives.** `aabb.py`, `intersect.py`, `fillet.py`,
   `polygon.py`, plus `ArcSegment.s_at_angle`. Nothing above `geometry` changes
   behaviour.~~ **done**
3. ~~**`ui/` and `modes/`.** Widgets, bars generated from registries, road
   swatches, view and road modes, `scenes/game.py` as the new default.~~ **done**
4. **Previews that show the real road.** `ToolPreview` grows ghosts, guides,
   measurements, highlights, anchors and a rejection reason; `road/cap.py`;
   `road/anchor.py`; `editor/guides/`; the overlay and snapper `if`-chains become
   registries. The previous slice added `editor/guides.py`: horizontal, vertical
   and road-extension alignment guides drawn dashed in the overlay while
   drawing, plus a rejection reason carried on `ToolPreview` itself (not just
   `ctx.status`) so a blocked road shows why, next to where it was refused. The
   current slice adds `road/cap.py` (item 8): a dead end derives a `Cap` from its
   one segment end, rebuilt alongside junctions whenever its node is dirty. A
   two-way road gets a **turning head** - a semicircular bulge tangent to both
   edges, exactly as wide as the road and no wider, so no trim or width change is
   needed - a one-way road gets a **terminal**, just a stop line. Squared-off dead
   ends are gone from `render/network_renderer.py`.

   The slice after that adds `road/anchor.py` (item 12's other half): one
   `Anchor` per vehicle lane at each segment end, sitting exactly on that lane's
   own centreline rather than the road's. `Snapper` gains a matching `ANCHOR`
   snap kind - checked after `NODE` but before the plain `SEGMENT` snap, and
   still `is_free` like `GRID`/`ANGLE`, since it only offers a position and a
   heading (D5) - the endpoint it seeds is an ordinary free node, never a lane
   connection. A road drawn off the end of a two-lane road now lines up with
   the lane it continues instead of snapping back to the centreline.

5. **Tool modes, loops, bulldoze, replace.** `editor/shapers/`;
   `editor/road_build.py`; `editor/impact.py`; the bulldoze and replace tools.
6. **Levels, colliders, crossings.** `level` and the corner pulls stored together
   (schema v2, once); `road/collider.py`; `road/spatial.py`; `road/crossing.py`;
   `road/validate.py`.
7. **Junction quality.** Exact trims, then rounded corners, then the corner
   handle, then pavements, then `render/junction_renderer.py` - in that order.
8. **Docs.** This file's tick-offs, D9-D13, the roadmap, `CLAUDE.md`.

---

## Defects found while planning

Three, all verified in the code, all fixed in step 1.

**D-1. Lane ribbons invert in tight curves - the pavement artifact.**
`build_ribbon` displaces the centre frame sideways (`geometry/ribbon.py`); it does
not call `arc.offset`. When a lateral offset exceeds the arc radius on the inside
of a curve, that edge folds _through_ the arc centre and the outline self-crosses -
and `pygame.draw.polygon` renders a self-crossing outline as holes and bowties.
Sidewalks carry the largest offsets (`asymmetric_boulevard` reaches 8.25 m), so
they fold first. The same curve raises `DegenerateOffsetError` on the exact
`path.offset` route, so one fix serves both: a derived `is_degenerate` flag the
renderer checks beside `is_too_short`, and a validator that refuses the road at
draw time. `fit_polyline` clamps a fillet against its neighbouring straights but
knows nothing about how wide the road is, so nothing upstream ruled this out.

**D-2. `RoadProfile.mirrored()` corrupted the save file.** It kept the same
`name`, and `network_to_dict` keys profiles by name - so a network holding both a
profile and its mirror wrote **one** entry and both roads loaded as whichever won.
Nothing triggered it because nothing called `mirrored()` outside tests; "right-click
flips direction" (item 5) is exactly `SetProfile(profile.mirrored())`, so that
feature would have shipped the corruption. Mirroring now suffixes the name, and
mirroring twice strips it again, so a flip-and-flip-back round trip stays
byte-identical.

**D-3. Panning: a stuck-state defect and a bindings gap.** `Camera.pan_pixels` was
correct and covered; `_panning` was only cleared by a `MOUSEBUTTONUP` _inside_ the
window, so releasing off-window or alt-tabbing mid-drag panned forever on the next
mouse move. And middle-drag was the only binding, which on a trackpad reads as
panning being broken outright.

---

## Module design

### `geometry/` - four new modules, pure and exact

```python
# aabb.py       the cheap "no" in front of every expensive query
Aabb(min, max)                       # of, expanded, union, intersects, contains
curve_bounds(curve) -> Aabb          # arc box is CLOSED-FORM, never sampled
path_bounds(path) -> Aabb

# intersect.py  the foundation under items 10, 13, 15 and the exact-trim debt
Hit(point, s_a, s_b)                 # arc length on BOTH curves
ray_ray / line_line / line_arc / arc_arc / arcs_overlap / curve_curve
path_intersections(p, q) / path_self_intersections(p) / path_touches(p, q)

# fillet.py     fit_polyline's corner maths, extracted for three callers
corner_fillet(corner, into, out_of, radius, room_in, room_out) -> Fillet | None

# polygon.py    for hovering a junction surface
signed_area / is_ccw / contains
```

Two traps, both of which produce a _plausible junction in the wrong place_ rather
than an error, so both have their own tests:

- **Containment goes through `ArcSegment.s_at_angle`, never `project`.** `project`
  clamps to the nearer endpoint, so it answers "yes, at the corner" for points the
  arc never reaches.
- **A hit on a join is found twice**, once per adjoining piece, so
  `path_intersections` dedupes - otherwise a road gets split twice a hair apart
  with a sliver between the cuts.

An arc's bounding box is the endpoints plus whichever of the four axis extremes the
sweep actually covers. Sampled boxes miss the bulge between samples, and every
rejection test downstream is only sound if the box is a true bound.

`fillet.py` is a behaviour-identical extraction: `tests/test_fitting.py` passes
**unchanged**, which is the proof.

### `road/` - what is stored and what is derived

Only **three** new stored fields in the whole milestone, all in schema v2:

```python
RoadNode.level: int = 0                  # storeys; metres are derived
RoadSegment.pull_a: float | None = None  # corner handle, None = derive it
RoadSegment.pull_b: float | None = None
```

Everything else is derived and rebuilt with dirty nodes (D10) - colliders,
crossings, the spatial index, junction corners, pavements, caps, trims, paths. A
stored collider is exactly the stale-derived-geometry failure D5 forbids: every
node drag, profile change and split would have to remember to invalidate it, and
one miss is a network that collides wrongly _and saves to disk_. "A collider at
build time" therefore means rebuild time.

```python
# collider.py   derived, cached beside `path`
Collider(segment_id, bounds, left, right, level_a, level_b)   # left/right are
                                    # EXACT offset Paths (D1), not polygon soup
# spatial.py    uniform grid, derived
SpatialIndex.candidates(bounds) -> frozenset[int]
# crossing.py   pure model
find_crossings(network, path, levels, *, ignore) -> tuple[Crossing, ...]
# validate.py   a registry of rules, not a branch anywhere
VALIDATORS = [_min_length, _min_radius_for_width, _self_intersection,
              _overlaps_same_level, _carriageway_survives_its_junctions]
# cap.py        TURNING_HEAD (two-way bulb) / TERMINAL (one-way, stop bar)
# anchor.py     lane-aware snap anchors, derived
# pavement.py   concentric fillet arcs carrying the footway round a corner
```

Notes that will save an afternoon:

- `_self_intersection` must run on the **carriageway edges** as well as the
  centreline. A wide road overlaps itself in a hairpin whose centreline never
  crosses - that case is the whole reason `intersect.py` exists.
- `_overlaps_same_level` tells a legitimate transverse crossing from a road lying
  on top of another by the crossing **angle**, not by hit count.
- A crossing within `config.CROSSING_MERGE_M` of an existing node is a node snap,
  not a crossing; two crossings closer than that collapse to one. Otherwise
  drawing through a junction leaves a second node a centimetre away, and splitting
  twice inside one fillet leaves two segments that immediately flag `is_too_short`.
- A cap contributes **no trim**. Dead ends trim nothing today and that invariant
  must survive, or every existing dead-end test moves.
- A lane anchor is an **alignment aid**, not a topological relation: it positions
  the new road's endpoint and seeds its direction, and the connection still
  resolves to an ordinary segment split or a free node. Lane-to-lane connectivity
  is M4, and D5 already reserves it.

### `editor/` - shapers, and a preview that is still data

A shaper owns its own _click grammar_ - straight is two clicks, curve is three,
freeform is a drag, continuous is an open chain. Leaving the grammar in
`DrawRoadTool` is precisely the `if`-tree rule 2 forbids, so:

```python
class Shaper(ABC):          # editor/shapers/base.py, one file per shape
    reset / set_cursor / add_point / undo_point
    begin_stroke / extend_stroke / end_stroke
    is_complete / is_continuous
    control_points() -> list[Vec2]      # what AddSegment stores
    guides() -> list[Guide]             # item 7 comes from HERE
    radius() -> float
```

`DrawRoadTool` shrinks to: own the active shaper, snap the cursor, feed it, ask for
`control_points()`, call `plan_road`, assemble the preview. No shape knowledge at
all. A shaper test is points in, a `Path` and guides out - no context, no camera,
no mouse.

`ToolPreview` grows, and stays pure data under three rules:

1. **A ghost carries a `Path` + `RoadProfile`, never a `Ribbon`.** A ribbon needs a
   tolerance, tolerance is `camera.world_tolerance` (D7), and a tool that built
   ribbons would have silently chosen a zoom - it would have half-become a
   renderer. `editor/overlay.py` builds the ribbons.
2. **A highlight carries ids and arc-length spans, not polygons.** A span survives
   a rebuild; a polygon does not.
3. **A measurement carries a number, not a string.** The overlay formats, so a test
   asserts `value == approx(length)` rather than parsing `"127.3 m"`.

Bulldoze's highlight comes from `editor/impact.py`, the same plan the command
executes (`RemoveSegment` already removes orphaned nodes), so "the highlight is
what happens" is true by construction rather than by two pieces of code agreeing.

Right-click flip needs **no new command**: `SetProfile(profile.mirrored())` is the
whole feature. For a symmetric two-way profile `mirrored()` is the identity; for a
one-way it flips travel without moving the pavements.

### `ui/` and `modes/` - above `editor`, not beside it

The layering line becomes:

```
geometry -> road -> render -> editor -> ui -> modes -> scenes / app
```

`ui/` is widgets and layout; `modes/` is ways of using the world. Shared state is
the existing `EditorContext` - it already owns everything every mode needs, and a
view mode is simply one that never calls `apply()`. A parallel state object would
immediately raise the question of which one owns the network.

**Event order, first consumer wins:** window (quit/resize/F1) -> `UiScreen`
(consumes everything over chrome, `MOUSEWHEEL` included, so scrolling the road bar
does not zoom the world) -> scene-level keys -> active `Mode` -> its `Toolbox` ->
active `Tool` -> `CameraController` **last**, so a tool always gets first refusal
on a button.

**Every bar is generated from a registry** - `PROFILES`, `TOOLS`, `SHAPERS`,
`MODES`. No hardcoded button list anywhere in `ui/`. That is rule 2 finally paying
the interface as well as the model: a new tool, shaper, mode or profile appears on
screen for free, and `tests/test_ui.py` asserts it against the registries so a
hardcoded list fails.

---

## Tests to write

Geometry stays at `EXACT = 1e-9`. Invariants, not implementations.

- **intersect** - a hit's point agrees from both parameterisations; symmetry under
  argument swap; a tangent yields exactly one hit at radius distance; an arc whose
  _extension_ would cross reports nothing (the `project`-clamping trap); a join hit
  appears once; a figure-eight self-intersects exactly once, a monotone road not at
  all, and a closed loop meeting only at its own corner not at all either.
- **aabb** - a path box contains 10 000 samples **and** is tight to 1e-9; an arc
  box catches a bulge between its endpoints; a full circle is bounded by the circle.
- **fillet** - the arc is exactly tangent to both legs; the sharper the turn the
  more straight it eats; the tighter side binds; below `MIN_RADIUS` it is a kink.
- **camera input** - a drag moves the centre exactly `(-dx/zoom, +dy/zoom)`; held
  keys move exactly `speed * dt`; a diagonal is not 1.41x faster; pan speed is
  constant on screen at any zoom; focus loss mid-drag stops the pan.
- **ui** - swatch stripes are proportional and sum _exactly_ to the rect; each bar
  has one button per registry entry; the wheel over chrome never reaches the camera.
- **modes** - switching preserves network identity, history depth and the payload;
  view mode clicks inspect and never mutate; leaving mid-road abandons the road and
  mutates nothing; Shift+digit switches mode while plain digits stay with tools.
- **crossing** - a same-height crossing is reported at the exact intersection; the
  same pair at different levels reports none; one within `CROSSING_MERGE_M` of a
  node reports none; results sorted by `s_new`.
- **spatial** - `candidates` is a **superset** of a brute-force scan (an invariant
  that survives a rewrite to a BVH; asserting bucket contents would not).
- **validate** - asserts `Violation.code`, never prose: a hairpin under the widest
  preset's half-width, a self-crossing freehand, a road whose _edges_ cross though
  its centreline does not, and a near-parallel overlap at the same level - all
  refused; the same road one level up accepted.
- **junction** - every M2 assertion intact, especially the asymmetric
  `node_a`/`node_b` case, which is the regression net for the trim rewrite; a
  corner fillet tangent to both kerbs to `EXACT`; pulling a handle out increases
  that arm's trim and radius monotonically to the clamp, and `None` reproduces the
  derived default exactly.
- **pavement** - the band's arcs are concentric and exactly one sidewalk width
  apart at every sampled angle; no sidewalk on a side yields no band.
- **serialization** - v2 round-trip byte-identical; a v1 payload loads with
  `level == 0` and `pull is None`; an unknown version still raises.

---

## Deferred, deliberately

- Pedestrian **crossings** across junction mouths - M4. Pavement _continuity_ is in.
- **Lane-to-lane connectivity** - M4; D5 reserves it. Anchors stay an alignment aid.
- **Level transitions along a segment.** A ramp is two nodes at different levels,
  drawn but not smoothed or banked.
- **Bridge presentation** - pillars, shadows, elevation shading. One cue only: paint
  order by level, and the level in the readout.
- **Handle-editing a placed road's shape** by dragging its control points. Freehand
  already covers freeform _drawing_; editing a placed shape is its own milestone.
- **Moving `Snapper` onto `SpatialIndex`.** Build the index for crossings; leave the
  snapper alone. A faster snapper that snaps differently is a regression.

---

## Done when

You can look at the network without being able to touch it, switch to roads, pick a
type off the bottom bar and see its cross-section, draw with straight / curve /
freeform / continuous with the real road previewed and its length and angle called
out, draw a loop back to your own start, draw across an existing road and watch a
junction form in one action, raise one road a level and watch the same crossing
become an overpass instead, be refused a road that folds through itself, hover the
bulldozer and see exactly what it would take, drag a junction corner handle and
watch that mouth open up and sweep, undo the lot, save, quit, reload, and get the
same network back - with `uv run pytest` green.
