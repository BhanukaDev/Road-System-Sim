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
subclass. Nothing above the kernel cares, _provided_ `sample(s)` stays
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

| Case         | Profile                                                  |
| ------------ | -------------------------------------------------------- |
| Two-way      | `[BACKWARD, FORWARD]`                                    |
| One-way      | `[FORWARD, FORWARD]` - no backward lanes exist           |
| Asymmetric   | unequal counts or widths, or a sidewalk on one side only |
| Tram in road | a `TRAM` lane between `CAR` lanes                        |
| Rail line    | only `RAIL` lanes                                        |

The alternative - `is_oneway`, `has_tram`, `lanes_left`, `lanes_right` flags -
collapses the moment you want a tram lane between two car lanes, or a bus lane on
one side. Adding a lane _type_ must never require a new field.

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

Lane-to-lane _connections_ inside a junction (M4) are different: those carry user
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
  "neither knows the other" is not available; only the _direction_ is.

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

---

## D9. `ui` sits above `editor`, and a mode is a way of using one world

**The shape:** `geometry -> road -> render -> editor -> ui -> modes -> scenes`.

An interface that drives the editor depends on it, so it sits above it. This is
D8's argument one layer further out, and the same test applies: if `editor` ever
needs to import from `ui`, that is the signal to stop and invert deliberately
rather than adding one import.

**Modes share one `EditorContext`.** A view mode is not a different world from an
edit mode; it is the same world with no mutations, and it enforces that by simply
never calling `apply()`. The alternative - a state object per mode - raises the
question of which one owns the network the moment there are two, and there is only
one right answer to that. `EditorContext` already carries exactly the set every
mode needs (network, camera, history, snapper, selection, cursor, status, active
profile), so the name now means _the session_. Renaming it would be churn across
every tool and test for nothing.

**Event order, first consumer wins:** window, then `UiScreen`, then scene-level
keys, then the active mode and its tools, then the camera. Two consequences worth
stating because both are bugs if you get them backwards:

- **Chrome consumes everything over it, the wheel included.** Scrolling the road
  bar must not zoom the world behind it, and the scene asks `ui.wants(pos)` before
  touching the cursor - otherwise a tool previews a road underneath the bar.
- **The camera goes last.** A tool always gets first refusal on a button, so a new
  tool can claim one without the camera having to know.

**Every bar is generated from a registry** - `PROFILES`, `TOOLS`, `SHAPERS`,
`MODES`. This is rule 2 paying the interface as well as the model: a new tool,
shaper, mode or road type appears on screen for free. `tests/test_ui.py` asserts
the bars against the registries, so a hardcoded button list fails the suite.

---

## D10. Camera _control_ is a controller, not an event ladder

**What this replaces:** pan and zoom wired directly into `app.py`'s event loop.

Two things were wrong with that, and only one of them was visible. The visible one
was the bindings - middle-drag alone, which on a trackpad reads as panning being
broken. The other was that a drag has **state**, and state only cleared by a
`MOUSEBUTTONUP` _inside_ the window gets stuck: release off-window or alt-tab
mid-drag and the camera panned forever afterwards.

`CameraController` lives in `render/` because it knows only `Camera` and pygame,
and it takes `cancel()` from the window's own focus events. The real payoff is
that it can be driven from a test with synthetic events and no window, which is
how the control the user touches most finally got covered at all.

**Pan speeds are in pixels per second, converted through `camera.zoom`** - the
same reasoning as D8's snap radii. Metres per second would crawl when zoomed in
and fly when zoomed out, which reads as two different controls rather than one.

**Right-drag is deliberately not a pan.** It would have to be disambiguated from
right-click, which tools already use, and the only honest way to do that is to
replay synthetic events once a press turns out not to be a drag. WASD, the arrow
keys, the screen edge and middle-drag cover it without touching a tool's button.

---

## D11. A curve intersection is a `Hit` with an arc length on both curves

M2 approximated junction trimming by crossing the straight tangent _rays_ at a
node, and capped the result because nearly-parallel kerbs cross near infinity.
Exact curve-curve intersection retires both, and four other features turned out to
need the same primitive: detecting that a new road crosses an existing one,
refusing a road that overlaps itself, rounding a junction corner, and collision
detection generally. So it is one module, built alone, before any consumer.

**Both arc lengths, always.** A crossing is a place to _split_ a road, and a split
needs `s`. That the point agrees from either parameterisation is the module's
central invariant, asserted at `EXACT`.

**Containment goes through `ArcSegment.s_at_angle`, never `project`.** `project`
clamps to the nearer endpoint - so asking it whether a point lies on an arc reports
every point past the end as lying _at_ the end. Used for containment it turns
"these curves do not meet" into "they meet at the corner", which is a plausible
junction in the wrong place rather than a visible failure. This is the single most
likely bug in anything built on this module.

**A hit on a join is found twice**, once from each piece meeting there, so path
queries dedupe. Undeduped, a crossing at a join splits a road twice a hair apart
and leaves a sliver segment that immediately flags `is_too_short`.

**Bounding boxes are closed-form, never sampled.** A sampled box misses the bulge
between samples, and every rejection test built on it is only sound if the box is a
true bound. An arc's box is its endpoints plus whichever of the four axis extremes
its sweep actually covers.

---

## D12. A junction corner is filleted, and a corner handle is a tangent length

M2 trimmed a junction against the straight tangent _rays_ at a node, capped
against a shallow angle's crossing running off toward infinity, and left every
corner between two arms a flat cut. D11's exact curve intersection retires the
first part: `_pair_demand` now crosses each arm's own end piece, offset out to
its real kerb, and only falls back to the tangent ray when that local search
finds nothing - a kerb too near parallel to cross within the piece at all, or
whose offset would collapse the arc it comes from. The ray-and-cap pair does
not go away; a shallow angle is still real, and the cap is still what keeps it
from swallowing the roads feeding it.

**The corner itself is filleted with the same `corner_fillet` `fit_polyline`
already uses** - one function, three callers, so a lane edge, a drawn road's
corner and a junction's corner are tangent to their straights by the same
closed-form arithmetic. The room each side can give is the kerb it still has
*past* that crossing, bounded by the same max-trim budget, so the same clamp
that keeps `fit_polyline`'s fillets honest about a short leg keeps a junction's
corners honest about a stubby arm.

**The trim is the kerb crossing plus the fillet's tangent length**, which is why
`_solve_trims` solves the corner rather than leaving it to a second pass. An arc
tangent to both kerbs touches them *beyond* the point where those kerbs cross:
stop an end at the crossing itself and its mouth sits short of where the corner
begins, so the junction surface bulges past the mouth and the pavement band
floats off the kerb it is meant to continue - the two halves of the same off-by-
a-tangent-length. Pull each end back by that tangent instead and the corner arc
lands exactly on the mouth it was solved with, which is what lets both the
surface outline and the footway be built by splicing arcs between mouth corners
with no joining geometry at all.

**A corner handle's pull is a tangent length, not a radius** (`RoadSegment.
pull_a`/`pull_b`, `None` meaning derive it). `radius * tan(deflection / 2) ==
tangent_length` is `corner_fillet`'s own formula, inverted so a pull sets the
trim and the radius together: drag the handle out and the corner opens up to
match, rather than the radius staying pinned to a default while a straight run
opens up in between. A tangent length is also the thing the trim is written in,
so a pull moves the mouth by exactly what it says.

Pavement bands (`road/pavement.py`) follow the same fillet arc by one sidewalk
width, concentric by construction - `ArcSegment.offset` guarantees that, the
same guarantee every lane ribbon already relies on. *Which side* is not a
choice: a junction corner curves around a centre out in the empty corner the
roads leave, so the edge facing the carriageway is the larger radius. Offset it
the other way and the footway swings out into the block. A corner with no
sidewalk on either connecting arm gets no band, not an empty one.

**Schema note:** `pull_a`/`pull_b` are written now, ahead of the `level` field
the milestone plan bundled them with, because nothing about them needs a level
to exist. They are additive and optional - omitted entirely when unset - so the
save format did not need a version bump to gain them.
