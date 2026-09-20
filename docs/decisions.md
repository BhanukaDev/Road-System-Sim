# Decisions

Why things are the way they are. Read this before changing a foundation - each
of these was chosen against a specific alternative, and the reasoning matters
more than the code.

---

## D1. Roads are straights joined by circular arcs, not splines

**Alternatives considered:** cubic Bezier segments (what Cities: Skylines uses),
polylines with fillets.

**Why arcs won:** offsetting. A lane edge is the centreline offset sideways, and
every road problem downstream is an offsetting problem - asymmetric profiles,
tram lanes, junction trimming, kerbs, markings.

- Offset a line -> a line.
- Offset an arc -> an arc with radius `R - d * turn_sign`. Same centre, same
  angles.

Both are closed-form. Measured error across the whole kernel is ~1e-15 m.

Offsetting a Bezier, by contrast, has no exact solution: you approximate, and the
error compounds at exactly the places that hurt most - tight curves, wide roads,
junction mouths. Polyline offsets self-intersect on inside corners and need
cleanup passes.

**The cost we accepted:** freehand drawing is not directly representable.

**How that cost is paid:** `fit_freehand` simplifies a raw stroke
(Ramer-Douglas-Peucker) into corner points, then fillets the corners. A sine-wave
sketch comes out as ~19 alternating line/arc pieces and reads as a real road.
The tension between "organic" and "arc + line" turned out not to bite.

**If you ever need true splines** (a rail easement, say), add a `Curve`
subclass. Nothing above the kernel cares, *provided* `sample(s)` stays
arc-length correct and `offset(d)` is honest about its error.

---

## D2. Everything is parameterised by arc length, never an abstract `t`

A Bezier's `t` is not proportional to distance. If you place dashed markings by
`t`, they bunch up in the curves. Same for a vehicle moving at constant speed,
and for texture V coordinates.

So `Curve.sample(s)` takes metres, and `Path` maintains a global arc-length
parameter across its pieces. `flatten()` returns arc-length stations.

This is a hard constraint on any future curve type. An arc-length
parameterisation for a spline needs a lookup table - that is the price, and it is
why splines are not the default.

---

## D3. World space is +y up; only the camera flips it

Screen space is +y down. If that flip leaks into the model, handedness breaks:
`rot90` stops meaning "left", left turns start reading as right turns, and lane
ordering inverts. One flip, in `Camera`, nowhere else.

Corollary: `normal = tangent.rot90()` points **left**, so `offset(+d)` shifts
left and lane profiles are ordered left-to-right.

---

## D4. Lane profiles are a flat ordered list, not a set of flags

A `RoadProfile` is just `LaneSpec`s left to right. Every case in the brief falls
out with no special-casing:

| Case | Profile |
|---|---|
| Two-way | `[BACKWARD, FORWARD]` |
| One-way | `[FORWARD, FORWARD]` - no backward lanes exist |
| Asymmetric | unequal counts or widths, or a sidewalk on one side only |
| Tram in road | a `TRAM` lane between `CAR` lanes |
| Rail line | only `RAIL` lanes |

The alternative - `is_oneway`, `has_tram`, `lanes_left`, `lanes_right` flags -
collapses the moment you want a tram lane between two car lanes, or a bus lane on
one side. Adding a lane *type* must never require a new field.

**The datum** records where the profile's centre sits relative to the
centreline, so a road can be widened on one side without moving its centreline
(and therefore without moving its junctions).

---

## D5. Junctions are derived, never stored

A junction is recomputed from the node's segment ends whenever something dirty
touches it. Nothing about junction geometry is persisted.

Storing junctions means every node drag, profile change and road split has to
remember to invalidate them - and one missed invalidation is a corrupt network
that saves to disk. Deriving costs a rebuild; storing costs correctness.

Lane-to-lane *connections* inside a junction (M4) are different: those carry user
intent ("no left turn here") and **will** be stored, in a separate module, keyed
so geometry rebuilds cannot silently discard them.

---

## D6. Every mutation is a Command

Undo is not a feature to retrofit. Routing all network mutation through
`do`/`undo` objects makes undo free, keeps mutations named and testable, and
stops tools from reaching into the model ad hoc.

---

## D7. Flattening is tolerance-driven, not fixed-count

Curves are sampled adaptively against a **screen-space** tolerance
(`camera.world_tolerance`), so a curve stays smooth as you zoom in and cheap when
zoomed out. Fixed segment counts facet when you zoom in and waste vertices when
you zoom out.

Ribbons tighten the tolerance further on arcs in proportion to lane width: an
edge `w` outside a curve of radius `r` bulges `(r + w) / r` more than the
centreline, so without this the outermost lane of a tight curve facets visibly
while the centreline looks fine.

---

## D8. `editor` sits above `render`, not beside it

**The rule this replaces:** "`render` and `editor` both sit above `road` and know
nothing about each other."

That rule could not survive contact with an editor. Two things break it:

- **Snap radii are in pixels.** A snap radius in metres gets harder to hit the
  further you zoom out, which reads to the user as the editor being broken. So
  `Snapper` needs `camera.zoom`, and `Camera` lives in `render`.
- **The editor overlay draws editor state** - selection, snap marks, the
  in-progress road. Whichever package it lives in depends on the other, so
  "neither knows the other" is not available; only the *direction* is.

So the layering is a straight line: `geometry` -> `road` -> `render` -> `editor`.
`render` imports nothing from `editor`; the M2 sketch's
`render/editor_overlay.py` is `editor/overlay.py` instead.

**What the old rule was protecting, and how it is still protected.** The point
was never the package boundary - it was that tools must not turn into renderers.
That is kept by a narrower contract: a `Tool` returns a `ToolPreview` (paths,
points, a snap) and never touches a surface. `editor/overlay.py` is the only
file in `editor` that draws. So the M2 sketch's `Tool.draw_preview(surface)`
became `Tool.preview() -> ToolPreview`.

**What that buys beyond tidiness:** every tool is testable with no window open.
`tests/test_tools.py` drives drawing, splitting, dragging and repainting through
the real code path with no display, no event loop and no mouse.

**If you ever need `render` to know about a selection**, that is the signal this
decision was wrong - stop and invert it deliberately rather than adding one
import.
