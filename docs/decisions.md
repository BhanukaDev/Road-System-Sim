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

---

## D13. A shallow merge is a gore, and the nose radius was the other half of it

**The symptom:** a Y junction at a shallow angle - a ramp merge, and more
generally any road leaving another at a smooth angle - drew its two
carriageways through each other, with the footway stretched across both as a
long thin slab. It was not buildable.

**Two separate causes, both in `_pair_demand`.**

First, the trim. `JUNCTION_MAX_TRIM_FACTOR * half_width` has **no angle term**,
and a shallow merge's demand is all angle: two kerbs 10 degrees apart with 5.5 m
extents do not separate until ~63 m out. The cap stopped both mouths at ~16 m
and the arms overlapped for the intervening 46. Worse, the overlap was
*invisible* to the code - `_exact_apex` only searched the end piece, so the real
crossing was never found, `ray_ray` supplied a far apex, and `Curve.project`
clamped it silently back to the end of that piece. D11 warned that `project` is
not a containment test; this is that warning coming true one layer up.

Second, the corner. `corner_fillet` needs a tangent of `radius * tan(phi / 2)`,
and at `JUNCTION_CORNER_RADIUS` (6 m) with `phi` near 180 degrees that is ~69 m
of kerb. The room clamps it, the fitted radius collapses below `MIN_RADIUS`, and
the fillet returns `None`. So the wedge was a flat cut, and `pavement.py` fell
back to its straight-quad branch - which is where the slab came from. **The
fillet maths was never wrong. The radius asked for was.** A real gore nose is a
tight kerb, and at `GORE_NOSE_RADIUS` the tangent is a few metres and the arc
survives. The pavement band then follows it concentrically for free, by D12's
existing guarantee.

**What replaces the cap:** a budget that is the larger of the old width floor
and `JUNCTION_MAX_TRIM_FRACTION` of *each arm's own length*. Tying it to length
is what lets a long ramp hold the long gore it genuinely needs - a 10 degree
merge really is ~70 m of road - while a stub still cannot be eaten by its own
junction.

**And when even that is not enough, say so.** `Junction.is_degenerate` is the
alternative to trimming-to-fit-and-overlapping: a pair whose kerbs never
separate inside either road's budget, or a mouth ring that crosses itself
(`geometry/polygon.is_simple`, added for this). The junction is outlined in
`SEGMENT_ERROR` and nothing is derived from it - no fill, no pavement, no stop
line. Same discipline as `RoadSegment.is_degenerate`: flag it, never raise, and
never draw it inside out.

**The honest cost:** a shallow merge on short roads is now refused where it used
to be drawn. It was drawn *wrongly*, so this is the bug becoming visible rather
than a capability being lost - but it does mean the answer to "why won't my Y
build" is sometimes "these roads are too short for that angle", and the flag has
to say so loudly enough to be read that way.

**A test that asserted the bug.**
`test_exact_trim_follows_a_curved_kerb_instead_of_a_straight_tangent` pinned the
trim to `JUNCTION_MAX_TRIM_FACTOR * half_width` at `1e-6`. It passed for the
whole time the overlap existed, because it was asserting the cap rather than the
geometry. Worth remembering the shape of that: a test written against a
workaround holds the workaround in place.

---

## D14. A decal is converted to polygons offline, never rasterised at runtime

Turn arrows were hand-built triangles in the renderer - a bend angle per option
and a wing width - which is a drawing of an arrow rather than the marking a
driver actually sees.

The markings are now the Hong Kong TPDM shapes, converted **once, offline**
(`tools/import_markings.py`) into polygon rings in `road/decal_library.py`.

**Against the obvious alternative, loading SVG at runtime:** pygame-ce can do
it, so this was a real choice. Polygons won on three counts. The game keeps its
single dependency and never parses SVG. A polygon stays exact at any zoom, where
a sprite resamples - and "exact at any zoom" is the whole of D7. And rings port
to a 3D engine as meshes, where a raster decal would have to be re-authored;
this repo exists to get the model right *before* that port.

**Shapes are normalised, not scaled to metres** - centred, +y along travel,
exactly 1.0 long - so the real size stays in `config.py` with every other
tunable (rule 4) instead of being baked in at whatever scale the source sheet
used. Scaling is uniform: a lane too narrow for an arrow gets a shorter one, not
a thinner one, because a squashed marking is a different marking.

**The y flip belongs in the importer**, at the edge where foreign data arrives.
SVG is y-down and the world is y-up (D3), and the camera owns the only other
flip in the codebase. A second one anywhere near it is how handedness bugs start.

**Licensing is unresolved and recorded as such.** The source repository carries
no LICENSE and the drawings derive from a government standard. Only the eight
markings actually used are converted, what ships is a derived outline rather
than the source file, and `assets/markings/ATTRIBUTION.md` records the origin,
the commit, and the fact that the codes are unnamed - so the identification is a
human judgement that can be checked rather than a fact to be trusted.

---

## D15. Paint across a lane transition is geometric, and is not connectivity

Two arms of different profiles already built a junction and already drew a
transition patch. What they had no answer for was paint: per-segment markings
stop at each mouth, so a 2-lanes-become-4 came out as bare asphalt.

`road/transition.py` pairs the two cross-sections' markings and carries them
across. Three things make it work:

- **The anchor is the centre line**, or the datum when there is none. Lining up
  on zero would be wrong for any widened road; the datum is where a profile
  says its own centre is (D4).
- **A centre line goes into both sides' lists**, not neither. That is what makes
  the case this exists for come out right: a median-split road meeting a
  paint-split one needs *both* median edges to reach that single line. Keep it
  out and the median stops in mid-air.
- **Surplus lines taper to the kerb**, because a road gains a lane against its
  kerb - which is where that lane has no width yet.

**The flip.** Each mouth's frame keeps its own segment's A -> B tangent, so two
arms drawn in opposite directions have opposing normals and their `+left`
offsets mean opposite sides of the same tarmac. One flip, computed once from the
two normals. The alternative - a sign on every comparison - is the same class of
mistake D3 exists to prevent.

**What this is not.** The pairing is geometric, for painting only. It carries no
user intent, nothing is stored, and it says nothing about which lane may feed
which. That is lane-to-lane connectivity, which D5 reserves for M4/M5 *precisely
because it does carry intent*. This module answers "where does this line go",
never "may I drive here", and it must not drift into the second question just
because it already has a lane correspondence lying around.

---

## D16. Handedness is a lane *order*, not a lane direction

`config.DRIVE_ON_LEFT` has exactly one consumer: `presets.py` reverses each
preset's lane list.

**The alternative that looks equivalent and is not:** flipping every vehicle
lane's `direction`. On a two-way street the two are the same picture. On a
one-way street they are not - flipping directions sends `one_way_two_lane`
B -> A, reversing a road against the direction it was drawn in rather than
mirroring it. Which side a travel direction keeps to is a question about
*order*; reversing the list is the whole answer, and it leaves types, widths and
the profile's name alone, so `mirrored()`'s name involution still holds.

**`turn_arrows.py` deliberately does not read the flag.** "You turn left from
the leftmost lane of your own direction group, and right from the rightmost" is
true under both conventions - what changes is which of those edges is the kerb
and which is the centreline, and the reversed lane order already says that. The
first draft threaded the flag through here too; it would have been a second
source of truth for the same fact.

**Stop lines do not read it either**, for a related reason: which lanes approach
a mouth is a question about travel direction, not about handedness. Traffic
reaching end A is the `BACKWARD` group whichever side of the road it keeps to.

**No schema change.** `serialization/schema.py` writes every `LaneSpec` in full,
so a network keeps the handedness it was built with and an existing save still
loads correctly after the flag flips.

## D17. A junction kerb is a blend between the mouths, not a fillet at their apex

**The symptom:** two roads meeting at an angle - one road bending, or changing
cross-section, at a two-arm node - drew a grey triangular wedge across the bend
with the footway stopping dead on either side of it. A gore nose by any other
name, except with straight edges and a hole where the pavement should be.

**Why the corner fillet was not the kerb.** `_pair_demand` solves a fillet at
the *apex* where the two kerbs cross, and the trim is then `reach + tangent`, so
the mouth lands exactly where that arc leaves the kerb. That invariant is real,
but it is conditional, and three things break it:

* the half-width floor - `max(reach + tangent, half_width)` - which wins
  whenever the arms are wide relative to how far apart their kerbs cross;
* `_trim_budget`, which clamps `reach` on a short arm;
* an arm still curving at its mouth, whose frame has turned away from the
  tangent ray the apex was found on.

In every one of those the mouth moves and the fillet does not follow. The arc
then floats somewhere inside the junction and `_rounded_outline` falls back to a
chord between the mouths - the triangle - while `build_pavement_bands` lays a
footway along an arc that no longer touches either road. **Nothing in the fillet
maths was wrong. It was answering a different question from the one being
drawn.**

**The two questions, separated.** The fillet stays exactly where it was and
keeps its job: its tangent length is a *budget*, the thing that tells each mouth
how far to pull back. What gets drawn is now a separate `Junction.blends` entry
per corner - a biarc from one mouth's kerb corner to the next, taking each end's
own mouth frame as its heading.

**Why a biarc.** The two endpoints and both directions are all fixed before the
kerb is built, and no single arc passes through two points with two prescribed
tangents. Two tangent arcs are the minimum that can, which makes this the
standard construction rather than a taste in curves - and they are arcs, so D1's
exact offset still holds and the pavement band is `blend.offset(width)` with no
resampling. The equal-chord variant shares the turning between the two arcs,
which is what gives a shallow merge the symmetric nose a real gore has instead
of one arc doing all the work.

**Curvature now comes from the orientations, not from a constant.** How far the
kerb bows is set by how far apart the two mouths are and how much their headings
disagree. A right-angle corner gets a quarter turn; two arms 10 degrees apart
get a long shallow nose; two profiles meeting head on get an S-bend stepping the
footway across the width change, where the old code cut a diagonal.

**A two-arm node is not a crossing, and is no longer coloured as one.**
`Junction.is_crossing` already knew the difference and only the crosswalk code
read it. The surface now takes `Color.JOINT_FILL` - the carriageway colour -
below three arms, because a road bending is road, not an intersection. That is
the whole of the fix for "it looks like a grey slab laid over my road".

**What this does not yet do:** the joint patch is filled as one slab of
carriageway, so a parking lane, median or bus lane running into it stops at the
mouth rather than continuing through. Continuing them needs lane-to-lane
correspondence across two profiles, which is `road/transition.py`'s problem and
is still only solved for paint.

**The tests changed shape, not strength.** `tests/test_pavement.py` asserted
concentricity - one centre, two radii - which is a property of the *fillet*, not
of a kerb. A biarc has no single centre, so the invariant is now stated as the
thing a pedestrian would notice: `inner` is exactly one sidewalk width from the
kerb at every point along it, measured by projecting back onto the kerb rather
than by arc-length fraction (offsetting an arc changes its length, so equal
fractions are not equal points).

## D18. A node drag is grabbed by a lever, frozen at grab time

**The symptom item 12 names:** snapping was centre-only, so a 2-lane road
joining a 4-lane one always landed centre-on-centre - there was nothing else on
a node to take hold of.

**The model.** `road/lane_handle.py` adds one handle per lane and one per lane
boundary (`LaneHandleKind.LANE` / `EDGE`) at each end of a segment, sitting on
the node's own *untrimmed* end (`path.sample(0.0)` / `path.sample(length)`),
never the trimmed carriageway end an `Anchor` uses. The trim is derived from the
junction and is rebuilt every frame a drag runs, including because of the drag
itself - a handle built from it would shift under the cursor while held.

**The lever, not a flip term.** Grabbing a handle records
`lever = handle.position - node.position`, frozen at the moment of the grab.
Dragging computes `node.position = drop.position - lever` every step, so the
node - not the handle - is what actually moves, and the handle rides along at
a fixed offset from it, exactly like the plain centre handle already did
(`lever = Vec2(0, 0)` is that case, unchanged). Because both the grabbed point
and the drop point are resolved to absolute world positions before anything is
subtracted, there is no per-frame sign to get right depending on which way
either road was drawn - unlike `road/transition.py`'s `flip`, which exists
because *that* module maps a signed profile offset out of one segment's frame
and into another's. A lever never does that, so it needs no flip, in any of the
four combinations of which end of which road is grabbed and targeted (tests in
`tests/test_lane_handle.py`).

**Where the state lives.** A grab is `editor/node_grab.NodeGrab` - `node_id`,
`origin`, `lever`, and the `LaneHandle` it came from for the HUD only. It lives
on the tool for the length of the drag and touches `RoadNode`, `Selection` and
every `Command` not at all: what lands in history is a plain
`MoveNode(node_id, final_position)`, the same command the centre handle has
always produced. Lane-aware dragging therefore costs nothing in serialization,
undo/redo, or any other model this milestone's D5 already protects.

**The frozen-lever residual, accepted rather than hidden.** The lever is
correct only for the tangent it was measured against. If the node's *other*
end is fixed elsewhere and the drag rotates the segment, the handle's true
post-move offset differs slightly from the one the lever assumed, by
`|offset| * (1 - cos Δθ)` for a rotation of `Δθ`. Recomputing the lever every
step removes the residual but creates a worse problem - the target keeps moving
as the segment keeps turning to chase it, which can fail to converge at all.
Freezing it is the same trade a physical lever makes: sub-millimetre on an
ordinary drag, visible only on a violent one, and always resolved the instant
the mouse is released and the node's real tangent is whatever the user left it
as. Nothing currently surfaces the residual live; a HUD readout of how far the
held lane is presently sitting from the cursor's own drop point is the natural
follow-up if it turns out to matter in practice.

## D19. Alt's three curve snaps do not arbitrate - they cannot conflict

`editor/curve_snap.py` gives a shape-handle drag (`editor/tools/shape_road.py`,
M3's un-deferred "handle-editing a placed road's shape") three things to snap
to while Alt is held: the point clinging to another road's tangent at a shared
node, the point's own turn rounding to `config.ANGLE_SNAP_DEG`, and a fillet's
radius rounding to a rung of `config.RADIUS_LADDER`.

**The radius snap was never going to compete with the other two - it acts on a
different variable.** `ARC_END` drags `segment.corner_radius`, a scalar;
`CONTROL`, `ARC_MID` and `STRAIGHT_MID` drag a point. A handle is one or the
other, never both, so `round_radius` and the two position snaps are simply
never asked the same question.

**Between the two position snaps, order is still a decision, not an
accident.** `CURVE_SNAPS = (tangent_continuity, heading_quantise)` - first
match wins. **Tangent continuity goes first because it is a claim about the
network, not about the one road being dragged.** A kink where two roads meet
at a node is visible from across the map; nothing else in this list can cause
it or cure it. Heading quantisation is a tidiness preference about a single
road in isolation - a corner that reads as a clean 45 rather than 43. A
15-degree-tidy road that still kinks at its own junction is a worse result
than a junction that flows with one untidy leg, so tangent continuity is
checked first and, where it applies, is the whole answer.

**Why they can genuinely disagree.** `tangent_continuity` only ever fires for
a control point adjacent to a node end (`index == 1` or
`index == len(points) - 2`) - the one place a kink can exist - and even there
only when another arm shares that node. `heading_quantise` has no such
restriction: it fires for any interior point with two real neighbours,
including the same one `tangent_continuity` claims. When both apply,
`tests/test_curve_snap.py::test_snap_curve_prefers_tangent_continuity_when_both_apply`
builds exactly that case and asserts the two candidates land at different
points before checking `snap_curve` picked the first.

**What this is not.** Nothing here decides which snap is *better* by any
geometric measure - the order is fixed, not scored, because scoring two
different kinds of correctness against each other (network-honest vs.
angle-tidy) has no principled answer. Fixed precedence is the same choice D3
made about `+left` being unconditional rather than resolved by a sign
comparison every time: one rule, applied in one place, rather than a decision
repeated - and possibly gotten wrong - at every call site.

## D20. Connecting two roads by lane is a merge plus a datum, not a position

**The symptom.** D18's lane handle lets a node's *position* line up with
another lane. That alone never produces the taper the feature was asked for -
a "5 lanes narrowing to 3, right-aligned" picture. The taper is
`road/transition.py`'s, and it only paints at a real two-arm junction: two
segments sharing one node. Position carries no alignment information once
that is true - a shared point is a shared point - so two roads sitting near
each other, each still with its own node, were never going to grow one.

**Two new primitives, because neither existed.** `RoadNetwork.merge_nodes`
(`road/network.py`) is the first thing in this codebase that connects two
*already-drawn* nodes - `add_segment` only ever attaches a segment to nodes
that already exist, and every snap that could have landed on another node
(`MoveNodeTool._target`) has always excluded that candidate on purpose,
because merging is a topology change a plain move must not casually cause.
`RoadProfile.with_datum` (`road/profile.py`) is `mirrored()`'s sibling: the
same cross-section, shifted sideways, named apart from its source for the
same reason D-2 fixed `mirrored()` - a save file keys profiles by name, and
two datums sharing one name is the same collision mirroring almost shipped.

**The datum must be computed *after* the merge, not before.** Which lanes end
up level with which is entirely a property of the dragged segment's tangent
at the shared node - and that tangent is only settled once its near control
point is actually pinned to the target's position and the path refits.
`editor/lane_connect.py` runs the merge once, unrecorded, to read the
resulting frame, computes the datum from it, then rewinds and hands back a
`Composite` that redoes both steps as the caller's one undo entry - the same
"do once to know the answer, then redo it recorded" shape `MoveNodeTool`
already uses one level up for the frozen lever itself.

**What "lining up" can and cannot mean.** For two roads meeting collinearly -
a road narrowing or widening as it continues, exactly the picture asked for -
the datum makes the chosen lane's *world position* land on the target's
exactly: both tangents are parallel or antiparallel at the shared node, so a
perpendicular offset in one frame is trivially the same line in the other,
sign aside. At a genuine angle - a real T or Y - no scalar shift can put an
arbitrary lane at an arbitrary world point; the two roads' "+left" directions
are no longer the same line at all. What the datum still guarantees there is
the one thing `road/transition.py` has always promised at any junction angle:
the chosen lane's own local offset matches the target's, flipped the same way
every other paired line at a joint already is. The exact-position claim is
the collinear case; the local-offset claim is the general one -
`tests/test_lane_connect.py` states both, and is explicit about where the
boundary sits rather than overclaiming the second as the first.

**Grabbing the plain centre handle never connects.** Only a drag that started
on a lane or edge handle reaches `connect_by_lane` at all
(`editor/tools/move_node.py:release`); dropping the centre handle on a lane
handle still just moves the node to that handle's position, exactly as
before D18. A centre-handle drag has no lane to align by, and D18's own
alignment claim - "profile unchanged, lanes still parallel" - is what that
handle was asked to keep meaning.

## D21. Lanes are picked while a road is drawn, not while a node is moved

**The symptom.** D20 put lane connection on the move tool: grab a node by one
of its lanes, drop it on another road's lane, and the two join. In use, that
is the wrong tool for it, for two reasons that pull in opposite directions.
Moving a node is a position question - "put it there" - and a node sprouting
eight or ten rings the moment the cursor nears it answers a question nobody
asked, obscuring the one handle the user actually wanted. Meanwhile the roads
being joined are usually not both there yet: the real gesture is *draw a
two-lane residential onto lane 2 of that four-lane*, a single stroke, and
splitting it into "draw, then move onto" is two undo steps for one intention.

So the lane handles moved to `tools/draw_road.py`, where picking one is the
point of the click, and `tools/move_node.py` went back to one node, one
handle, one question. D20's machinery is not repudiated - `road/lane_handle.py`
and `RoadProfile.with_datum` are exactly as D18 and D20 left them - only its
caller changed. `editor/lane_connect.py` went with the caller: joining two
*already-drawn* nodes has no gesture left that reaches it, and a module kept
alive by its tests alone is a second answer waiting to disagree with the first.
`RoadNetwork.merge_nodes` stays, tested in its own right, for the bulldoze and
replace work M3 still owes.

**Nothing is merged, so nothing has to be un-merged.** Drawing onto a lane
handle ends the road at that handle's *node* - `Snap.attach_node_id` and
`attach_position` say so for every snap kind at once, and `_endpoint` treats a
lane snap as the node snap it is. That is `AddSegment` attaching to an existing
node, which this editor has done since M2; the whole merge-then-rewind dance
D20 needed exists only because both nodes were already real. One `AddSegment`,
one undo step, and the alignment rides along in the profile the segment is
built with.

**The pairing is solved at commit, because that is when the road has a
direction.** A datum is a lateral offset, and lateral is only meaningful
relative to a frame; at the click that chooses the lane, the stroke may be a
single point with no heading at all. So `editor/lane_draw.py` is handed the
*fitted path* and answers both ends from it with one function, after the fact -
the same "solve it once the geometry is settled" shape D20 reached for with
its unrecorded merge, minus the merge.

**Nearest lane, not matching index.** The new road and the target generally
have different lane counts - a 2-lane joining a 4-lane is the case the feature
exists for - so index `k` names nothing shared. The picked handle is projected
into the new road's own end frame to a single lateral `t`, and the new
profile's own candidate offsets (lane centres and edges, the identical list
`road/lane_handle.py` publishes) are searched for the nearest. Because both
sides are resolved to world positions before anything is compared, no flip term
appears for any of the four end-to-end orientations - the same reason D18's
lever needs none.

**One datum, two ends, and the start wins.** A profile carries one datum and a
road has two ends, so a stroke that begins on one road's lane and finishes on
another's cannot honour both: lanes converging along a road is a taper, which
is `road/transition.py`'s and needs two segments. Rather than silently
averaging or quietly dropping one, `profile_for_lane_ends` states the rule -
the start, the end the user deliberately began from - and
`tests/test_lane_draw.py` pins it.

## D22. A preview is the network one command ahead, not a drawing of intent

**The symptom.** The draw tool's preview was a one-pixel centreline with lane
strips painted round it, and "invalid" was a flag set *after* a commit was
refused. So the user learned a road could not be built by pressing Enter and
watching nothing happen, and what the strip showed - a constant-width road
running straight into the target - was not what the commit built: the commit
split the target, trimmed three arms back to their kerbs, and put a turning
head on the far end. M3's item 6 ("a road preview is a one-pixel centreline,
not a road") and item 11 ("what you are connecting to") were both open, and
Cities: Skylines' ghost - translucent, showing the junction that will form,
red when it cannot - was the stated reference.

**Alternatives considered.** (a) Draw the previewed road better: lanes plus
markings plus a cap, computed from the path alone. (b) Write a validator that
mirrors the rules a commit will hit - too short, too tight, sharp angle - and
colour the strip by its verdict. (c) Build the road on a scratch copy of the
network, rebuild the junctions it touches, draw the changed part translucently,
and read validity off the result's own flags.

**Why (c).** The first two both re-derive, in the tool, things the model
already knows how to derive, and each is a second answer waiting to disagree
with the first. A preview drawn from the path alone cannot show a trim, because
a trim is a property of a junction, and a junction is derived from *all* the
arms at a node (D5). A validator that mirrors the commit's rules drifts from
them the day one side changes - and the rules that matter most here are not
threshold checks anyway but geometric outcomes: whether a gore resolves within
the budget both arms can give (D13), whether an inner lane edge folds through
its arc centre (`is_degenerate`), whether the carriageway left between two
junctions is more than nothing (`is_too_short`). Those are already flags the
renderer checks every frame. Building the ghost and reading the same flags
makes "the preview went red" and "the road drew as an error" one event.

**How.** `RoadNetwork.copy()` gives an independent network with the same next
ids - so the segment the ghost calls 7 is the segment the commit will call 7 -
sharing profiles, which are immutable, and copying nodes, segments and the
derived junctions and caps. `editor/ghost.py` applies the command to the copy,
reads the dirty set the command leaves behind (which is exactly the set
`rebuild_dirty` retrims, so one set scopes both the rebuild and the drawing),
rebuilds, and asks `road/validate.py` for the first problem among the touched
parts. `NetworkRenderer.draw` learned to draw a named subset - the same code
path, fewer things painted - and `editor/overlay.py` draws that subset onto a
per-pixel-alpha layer and blits it through once at `config.GHOST_ALPHA`. One
layer, one alpha, so overlapping ghost polygons do not double-darken at lane
boundaries. A ghost with a problem has `Color.GHOST_INVALID_TINT` added to
every pixel before the blit: still lanes, still a junction, unmistakably red.

**The one rule that is not a flag.** Two roads crossing without a node at the
crossing form nothing today - item 13, step 6's crossing detection. Until a
crossing *creates* a node it is refused, in `road/validate.py`, using
`geometry/intersect.py`'s `path_intersections` on the new road against every
other, skipping only the hit at a node both roads end on. That is the sole rule
the ghost carries that the model does not; when step 6 lands and a crossing
becomes a junction, the rule is deleted and nothing else moves.

**A fresh command for the commit.** A command remembers the ids it allocated so
that redo is byte-identical (`editor/commands.py`). The one the ghost ran has
therefore already *done* once, on the copy, and running it on the real network
would be a redo, not a first do. `plan_road` builds a new command each call -
once per frame for the preview, once more for the commit - which is cheap,
and it is what keeps the ghost's copy from ever leaking an id into the real
history. `tests/test_ghost.py` pins that the ghost's network and the committed
one serialise identically.

**Hovers are ids, not geometry.** `ToolPreview.highlights` carries the road
a `SEGMENT` snap would split or the node a `NODE`/`LANE` snap would join, as a
`Highlight(kind, id)`; the overlay looks the thing up and washes its real
carriageway. Carrying the id means the highlight cannot drift from the road it
names, and a test can assert what is lit with no window open - the same
argument `PreviewHandle` made for grabbable points. Before a first point there
is nothing to ghost, so `ToolPreview.footprint` shows the active profile's
width as a disc under the cursor: the road type reads before the road exists.

**Cost.** Copy, command, rebuild of two or three junctions and the crossing
check run in 2-4 ms per frame on the demo network, once per frame regardless
of how many motion events arrive. The layer is a full-window surface kept
between frames and cleared only when there is something to put on it.

## D23. A lane can be joined anywhere along a road, and a road can run alongside one

**The symptom.** D21 put lane handles at nodes, so a road could be drawn onto
a chosen lane of another road - but only where that road already ended. The
shape that motivated the feature, a ramp leaving a motorway from its outer lane
and running parallel to it, has no node where the ramp leaves: the motorway is
one long segment. Drawing onto it mid-way gave the centreline split of M2, a
road built to the *middle* of the carriageway, and the user then had nothing
to place the parallel run against but their eye. Three things were missing, and
the footprint disc made the first of them look worse than it was: aiming at a
lane handle put the disc on the node, because the road's centreline does end
there, so the disc said "centre" while the click meant "kerb".

**Handles at any station.** `road/lane_handle.py`'s handle is now built from
`segment.path.sample(station)` for any `station`; a handle at a node is the
special case `station in (0, length)` with `node_id` set, and the old
`segment_end_handles` is that wrapper. `Snapper.nearest_lane_handle` offers
the handles at the station the cursor projects to, anywhere over the
carriageway and within reach outside its kerbs, always the *nearest* lane line
rather than only one within a tight radius - so hovering a road always names a
lane and never falls through to a grid point that the ghost then flags for
crossing the road it is over. Within a node's own snap reach of either end the
node's handles keep the cursor to themselves, because two sets a few pixels
apart would fight, and a split that close would leave a stub.

A `LANE` snap along a road resolves the way D21's resolves at a node, plus one
step: `Snap.segment_hit` names the split, `_endpoint` makes it with the same
`SplitSegment` a centreline snap uses, and the new road joins the node the
split creates with its datum solved from the handle exactly as before -
`datum_for_lane_target` only ever read `handle.position`. One `Composite`, one
undo step. The pairing is still lateral in the new road's own end frame: a road
arriving square on sees the kerb *ahead* of it, not beside it, gets a lateral
of zero and joins by the centreline - which is the right answer for a T, and
`tests/test_lane_along_road.py` aims its merge shallow for that reason.

**The footprint sits where the body will be.** A profile's body is centred
`datum` to the left of its centreline (`RoadProfile.edges` is symmetric about
the datum), so `footprint_on_lane` puts the disc at the handle's centre plus
the datum that handle would produce, and the overlay draws it at half the
*total* width rather than the wider extent. The datum needs a frame and the
disc exists before the road has one, so it assumes the road leaves along the
target road's own tangent; that is what a continuation or a shallow ramp does,
and once a point is placed the ghost takes over with the exact answer.

**Alongside is kerb beside kerb, a verge apart, and nothing else.**
`SnapKind.BESIDE` pulls a free point sideways so the road being placed runs
parallel to a neighbouring road with `config.BESIDE_GAP` between the two
kerbs, and slides along it. It is an alignment aid with a free point, like
`ANCHOR` (D5), and it is only offered when the caller says what is being placed
- `Snapper.snap(..., beside=profiles)` - because "alongside" has no meaning
without a width. Only kerbs pair: every other pairing of one road's lane lines
with another's puts the two carriageways through each other, which is a
crossing to be drawn as one. Both of a profile's kerbs are tried against both
of the neighbour's, so the two roads may run either way. The point has to be
genuinely beside the road - a projection that clamped to an end is beyond it,
and extending a kerb line past a dead end stays `Anchor`'s job.

The verge is not zero, and the model and the world agree on why. Two
carriageways touching kerb to kerb are one wider carriageway with a lane line
down it - a transition (D15), not two roads - and a real ramp or service road
sits behind a verge or a barrier. The junction says the same: a ramp that
leaves a road and then runs touching it shares that road's kerb line, so
`road/junction.py` finds no crossing to close the gore at and flags the node
degenerate, while the same ramp two metres out resolves at the angles a ramp
leaves at. `BESIDE_GAP` is a tunable, and 0.0 snaps kerb against kerb for
whoever wants it.

**Both tools use it, with the profile that is true for them.** The draw tool
hands `snap()` the profile the road would be *built* with - the active one,
shifted by the start's lane if the stroke began on one - because a road that
started on a lane has had its kerbs moved by that datum, and solving the
parallel run for the unshifted profile leaves it a lane's width off. The datum
depends on the start frame, which two placed points fix before the end is
chosen, so the answer is exact for the ramp shape; with one point placed it is
the best estimate until the next click. The move tool hands over the profiles
of the roads meeting the dragged node. That is still one node, one handle, one
question (D21): the snap answers *where* the node goes and connects nothing.

**What did not change.** `editor/lane_draw.py`'s solver, the datum-in-the-name
rule (`RoadProfile.with_datum`), `SplitSegment`, and the ghost. The mid-road
join is the node join plus a split the editor already knew how to make.
