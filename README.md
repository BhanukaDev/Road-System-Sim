# Road System Sim

A 2D sandbox for working out the hard parts of a road network before any of it
goes near a 3D engine: organic road drawing, editor tooling, lane cross-sections
(two-way, one-way, asymmetric), junction geometry, texturing, tram lines, rail
and level crossings, then vehicles and road rules.

This is not the game. It is the place where the data model gets figured out.

## Run

```bash
uv sync
uv run road-sim                  # debug geometry scene
uv run road-sim --scene debug
```

`middle-drag` pans, `wheel` zooms, `Home` resets the view, `F1` toggles the HUD,
`Esc` quits.

In the debug scene: **click** to add a corner point, **drag** to sketch freehand,
**right-click** to reset. `N` normals, `S` stations, `C` arc centres, `L` lanes,
`R` cycles the fillet radius.

## Layout

```
src/roadsim/
  geometry/   pure maths. lines, arcs, paths, fitting, ribbons. no pygame.
  render/     camera, grid, curve drawing, HUD. reads the model, never writes.
  scenes/     modes. one Scene subclass each, registered in scenes/__init__.py.
  config.py   tunables and palette.
  app.py      window, loop, camera controls shared by every scene.
```

Three rules keep this from turning into one big file:

1. `geometry` knows nothing about roads; `road` (coming in M2) will know nothing
   about pygame; `render` and `editor` know about the layers below them and
   nothing about each other.
2. New behaviour is a new file plus one registry line, never an `if` branch in
   something large.
3. Every network mutation will go through a `Command` with `do`/`undo`.

## Geometry

Roads are **straights joined by circular arcs**, the way real roads are surveyed.
The payoff is in offsetting: offsetting a line gives a line, and offsetting an
arc gives another arc with radius `R - d`. Lane edges are therefore *exact*
rather than resampled, which is what makes asymmetric profiles, tram lanes and
junction trimming tractable instead of miserable.

Everything is parameterised by **arc length**, not an abstract `t`, so evenly
spaced markings, vehicles moving at a given speed, and texture V coordinates all
come for free.

Freehand drawing is bridged into this by `fit_freehand`: simplify the stroke to
corner points, then fillet the corners. A hand-drawn squiggle comes out looking
like a road.

Handedness: world space is +y **up** (the camera is the only place y flips), and
`normal = tangent.rot90()` points **left**. So `offset(+d)` shifts left.

## Docs

- `CLAUDE.md` - conventions and the layering rules
- `docs/decisions.md` - why arcs and not splines, why derived junctions, etc.
- `docs/roadmap.md` - milestones
- `docs/milestone-2-network-and-editor.md` - the next milestone, in detail

## Status

- [x] **M0** scaffolding: window, camera, adaptive grid, HUD
- [x] **M1** geometry kernel: `Curve`/`LineSegment`/`ArcSegment`/`Path`,
      tangent-arc-tangent fitting, ribbons, plus the debug scene that verifies it
- [ ] **M2** network + editor: lane profiles, topology, junction trimming,
      tools, undo/redo, JSON save/load
- [ ] **M3** textures & markings, rail, trams, level crossings
- [ ] **M4** lane graph, vehicles, road rules, pedestrians

## Tests

```bash
uv run pytest
```

Tests assert exactness (1e-9), not "looks about right" - closed-form geometry
has no excuse for drift. The `debug` scene is the visual counterpart: if offsets
stay parallel through arc/line joins, normal hairs never cross, and stations
stay evenly spaced at every zoom level, the kernel is sound.
