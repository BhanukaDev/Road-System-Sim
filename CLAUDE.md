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
uv run road-sim --scene debug
uv run pytest               # full suite
uv run pytest tests/test_arc.py -v
```

## Layout

```
src/roadsim/
  geometry/   pure maths: vec, curve, line, arc, path, fitting, ribbon
  road/       (M2) lanes, profiles, nodes, segments, junctions, network
  render/     camera, grid, curve drawing, HUD
  editor/     (M2) tools, commands/undo, snapping
  scenes/     one Scene subclass per mode, registered in scenes/__init__.py
  config.py   tunables and palette - no magic numbers elsewhere
  app.py      window, loop, camera controls shared by every scene
docs/         architecture, decisions, per-milestone design notes
tests/        pytest, geometry-focused
```

## The rules that keep this from becoming one big file

1. **Layering is one-directional.** `geometry` knows nothing about roads.
   `road` knows nothing about pygame. `render` and `editor` both sit above
   `road` and know nothing about *each other*. A renderer never mutates the
   model; a tool never blits.
2. **New behaviour is a new file plus one registry line**, never an `if` branch
   in something large. Tools register in `editor/toolbox.py`, scenes in
   `scenes/__init__.py`, lane types in `road/lane.py`.
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

## Testing

Tests assert **exactness** (`EXACT = 1e-9` in `tests/conftest.py`), not "looks
about right" - closed-form geometry has no excuse for drift. Cover the invariant,
not the implementation: *"lane edges stay exactly d from the centreline"*, not
*"offset() returns an ArcSegment"*.

The `debug` scene is the visual counterpart: offsets parallel through arc/line
joins, normal hairs that never cross, stations evenly spaced at every zoom.
Keep new geometry work visible there.

## Status

M0 scaffolding and M1 geometry kernel are **done**. M2 (network + editor) is
next - see `docs/milestone-2-network-and-editor.md` for the design, and
`docs/decisions.md` for why things are the way they are.
