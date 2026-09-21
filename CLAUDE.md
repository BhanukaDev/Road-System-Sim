# Road System Sim

A 2D pygame sandbox for solving road-network problems before they go near a 3D
engine. **This repo is not the game.** It exists to get the data model right for:
organic road drawing, editor tooling, lane cross-sections (two-way, one-way,
asymmetric), junction geometry, texturing, trams, rail, level crossings, then
vehicles, pedestrians and road rules - added one at a time.

Bias every decision toward *a model that will still hold when a feature lands
three milestones from now*, not toward the shortest path to something on screen.

## Commands

```bash
uv sync                     # install (pygame-ce + pytest)
uv run road-sim             # launch, default scene
uv run road-sim --scene network   # hardcoded showcase
uv run road-sim --scene debug
uv run pytest               # full suite
uv run pytest tests/test_arc.py -v
```

## Layout

```
src/roadsim/
  geometry/   pure maths: vec, curve, line, arc, path, fitting, ribbon, biarc
  road/       lanes, profiles, nodes, segments, junctions, network,
              markings, crosswalks, decals, lane transitions
  render/     camera, grid, curve drawing, network renderer, HUD
  editor/     commands/undo, snapping, tools, shapers, guides, overlay
  ui/         widgets, bars, panels - every bar generated from a registry
  modes/      ways of using the world (view, roads), in modes/__init__.py
  serialization/  versioned JSON schema and file io
  scenes/     one Scene subclass per app surface, in scenes/__init__.py
  config.py   tunables and palette - no magic numbers elsewhere
  app.py      window, loop, camera controls shared by every scene
tools/        offline build scripts, not shipped (SVG -> decal polygons)
assets/       provenance for anything converted from outside this repo
docs/         architecture, decisions, per-milestone design notes
tests/        pytest, geometry-focused
```

## The rules that keep this from becoming one big file

1. **Layering is one-directional:** `geometry` -> `road` -> `render` ->
   `editor` -> `ui` -> `modes` -> `scenes`. `geometry` knows nothing about roads;
   `road` knows nothing about pygame; `render` knows nothing about the editor; the
   interface drives the editor and never the reverse (D8, D9). A renderer never
   mutates the model, and a tool never blits - a tool returns a `ToolPreview` and
   `editor/overlay.py` is the only thing in `editor` that draws.
2. **New behaviour is a new file plus one registry line**, never an `if` branch
   in something large. Tools register in `editor/toolbox.py`, road shapes in
   `editor/shapers/__init__.py`, modes in `modes/__init__.py`, scenes in
   `scenes/__init__.py`, lane types in `road/lane.py`, curve-pair intersections in
   `geometry/intersect.py`, painted markings in `road/decal.py`. The interface
   is generated from those same registries,
   so a new entry appears on screen without `ui/` learning its name.
3. **Every network mutation goes through a `Command`** with `do`/`undo`
   (`editor/commands.py`, M2). No tool mutates the network directly.
4. **No magic numbers outside `config.py`.**

## Geometry conventions - read before touching anything

- **World space is metres, +y up.** The camera is the *only* place y flips for
  the screen. Do not sprinkle y-flips anywhere else.
- **`normal = tangent.rot90()`, which points LEFT.** So `offset(+d)` shifts
  left, `offset(-d)` right. Lane profiles are ordered left to right.
- **Everything is parameterised by arc length `s`, never an abstract `t`.**
  That is what makes evenly spaced markings, constant-speed vehicles and texture
  V coordinates fall out for free. If you add a curve type, `sample(s)` must be
  arc-length correct.
- **Roads are straights joined by circular arcs.** Offsetting a line gives a
  line; offsetting an arc gives an arc of radius `R - d*sign`. Lane edges are
  therefore *exact*. Never resample a centreline to build a lane edge - call
  `path.offset(d)` or `build_ribbon(...)`.
- **Flattening is adaptive and tolerance-driven.** Pass
  `camera.world_tolerance` so screen-space error stays constant as you zoom.
  Never hardcode a segment count.
- Freehand drawing goes through `fit_freehand`: simplify the stroke, then fillet
  the corners. That is how "organic" and "arc + line" coexist.
- **`project()` clamps to the nearer endpoint, so it is not a containment test.**
  Asking whether a point lies on an arc goes through `ArcSegment.s_at_angle`. Get
  this wrong and an intersection past the end of a curve is reported *at* its end -
  a plausible junction in the wrong place rather than a visible failure (D11).
- A curve is too tight for its own road when an inner lane edge folds through the
  arc centre. That is `is_degenerate`, checked by the renderer beside
  `is_too_short` - never an exception, and never a lane drawn inside out.

## Testing

Tests assert **exactness** (`EXACT = 1e-9` in `tests/conftest.py`), not "looks
about right" - closed-form geometry has no excuse for drift. Cover the invariant,
not the implementation: *"lane edges stay exactly d from the centreline"*, not
*"offset() returns an ArcSegment"*.

The `debug` scene is the visual counterpart: offsets parallel through arc/line
joins, normal hairs that never cross, stations evenly spaced at every zoom.
Keep new geometry work visible there.

## Status

M0, M1 and M2 are done: the geometry kernel, `road/` (profiles, segments,
network, derived junctions), the network renderer, `serialization/`, and
`editor/` (commands with undo, snapping, four tools).

**M3 - editor, UI and crossings - is in progress.** The design and the full
requirement list are in `docs/milestone-3-editor-and-ui.md`.

Landed so far:

- **Controls and crash safety.** `render/camera_input.py` owns pan and zoom -
  WASD, arrows, screen edge, middle-drag - and cancels a drag on focus loss.
  `RoadSegment.is_degenerate` flags a curve too tight for its own width instead
  of letting the renderer draw the lane inside out. `RoadProfile.mirrored()` no
  longer collides with its original in a save file.
- **Exact geometry.** `geometry/aabb.py`, `intersect.py`, `fillet.py`,
  `polygon.py`, plus `ArcSegment.s_at_angle`. `fit_polyline` delegates its corner
  maths to `fillet.py`, with `tests/test_fitting.py` passing unchanged as proof.
- **Game interface and modes.** `ui/` and `modes/`; `scenes/game.py` is the
  default scene, opening in view mode with a road mode beside it.
- **Markings that tell the truth about direction.** A stop line covers the
  approach half of a mouth only - the lanes arriving there - so the two ends of
  a road are marked on opposite halves instead of identically. Turn decals
  follow the same rule and appear only on approaching lanes. The zebra still
  spans the whole carriageway, because a pedestrian crosses all of it.
- **Shallow merges build.** A Y at a smooth angle used to draw both
  carriageways through each other with the footway slung across the pair.
  `road/junction.py` now searches the whole kerb for the real crossing, budgets
  the trim against each arm's own length rather than a width multiple, and
  rounds the wedge with a gore nose instead of asking for a corner radius that
  collapses. A node that still cannot resolve sets `Junction.is_degenerate` and
  is drawn loudly rather than overlapped (D13).
- **Real road decals.** `tools/import_markings.py` converts TPDM marking SVGs
  offline into polygon rings (`road/decal_library.py`); `road/decal.py` and
  `render/decal_renderer.py` place them. Nothing at runtime reads SVG. See
  `assets/markings/ATTRIBUTION.md` - **the source carries no licence**, so treat
  the shapes as placeholders until that is cleared (D14).
- **Lane transitions are painted.** `road/transition.py` carries markings across
  a 2-lanes-become-4 patch - the centre line, a median folding back onto it,
  tapering dividers - and puts a merge arrow where a lane runs out (D15).
- **Handedness.** `config.DRIVE_ON_LEFT`, default left. It reverses a preset's
  lane order and nothing else (D16).
- **Junction kerbs are blends, not chords.** `geometry/biarc.py` joins two
  points that each already have a heading, which is what a junction mouth is.
  `Junction.blends` runs one between every adjacent pair of mouths, so the kerb
  leaves each carriageway along that road's own tangent and bows by however much
  the two orientations disagree - a nose at a gore, a quarter turn at a right
  angle, an S-bend across a profile change. The pavement band is that blend
  offset by a footway's width, so sidewalks now run *through* a bend instead of
  stopping either side of it. Two arms meeting is a joint in one road, not a
  crossing, and is filled as carriageway (D17).
- **Nodes are grabbed by a lane, not only by their centre.** `road/lane_handle.py`
  adds one handle per lane and per lane edge at each end of a node, sitting on
  the *untrimmed* end so a live junction rebuild never moves it mid-drag.
  `editor/node_grab.py` and `MoveNodeTool` compute every drag - lane handle or
  the plain centre alike - as `node.position = drop.position - lever`, a lever
  frozen at grab time; because both ends are resolved to absolute world
  positions first, joining roads of different lane counts by a chosen lane or
  kerb needs no flip term in either direction (D18). Dropped *on another
  road's lane* rather than open space, the two roads actually connect:
  `road/network.py:merge_nodes` - the first thing here that joins two
  already-existing nodes - folds the dragged one into the target, and
  `editor/lane_connect.py` sets the dragged segment's `RoadProfile.datum`
  (`with_datum`, named apart from its source the way `mirrored()` is) so the
  chosen lane lines up, computed from the geometry only the merge settles.
  For two roads meeting collinearly - a road narrowing or widening as it
  continues - that lines up the lane's exact world position and the existing
  `road/transition.py` taper renders; at a real angle a single datum cannot
  do that, and the honest guarantee narrows to the lane's own local offset
  matching the target's, the same pairing every other junction already uses
  (D20).
- **A selected road's own shape is a set of real handles.** `road/shape_handle.py`
  derives one at every fillet's belly and both its tangent points, and at each
  straight's midpoint, from `segment.path.pieces` alone - looking changes
  nothing on disk. `editor/tools/shape_road.py` drags them, materialising a new
  control point only where none exists yet and provably without moving the road
  first. Alt holds a drag to tidy values - tangent continuity at a junction,
  then a quantised turn, then a rounded radius - in a fixed, un-arbitrated
  order because the three act on different things or answer different
  questions (D19).

Still to come: previews that show the real road, end caps, lane anchors and
alignment guides; shapers (straight / curve / freeform / continuous), loops,
bulldoze and replace; levels, colliders and crossings; then exact junction trims,
rounded corners, the corner handle and pavements.

`--scene editor` keeps M2's road-only shell, `--scene network` the hardcoded
showcase - which now includes a shallow gore and a lane taper - and
`--scene debug` M1's geometry surface.

See `docs/decisions.md` for why things are the way they are - D9 to D20 are this
milestone's.
