# Roadmap

Each milestone answers a question from the original brief. Nothing moves on
until the previous answer holds up visually *and* under test.

## M0 - Scaffolding - done

Window, camera (pan/zoom, adaptive grid), HUD, scene registry, `uv` project.

## M1 - Geometry kernel - done

`Curve` / `LineSegment` / `ArcSegment` / `Path`, tangent-arc-tangent fitting,
freehand stroke fitting, ribbons. Plus the `debug` scene that makes failures
visible and 101 tests that make them precise.

Answers: *how do you draw organic roads, and how do you get exact lane offsets?*

## M2 - Network + editor - done

`road/` topology, lane profiles, derived junctions, the `Tool`/`Command`
framework with undo, JSON save/load. Lanes render as flat colored polygons.

Answers: *two-way, one-way, asymmetric, tram and rail cross-sections; what
happens where roads meet.*

Design: `docs/milestone-2-network-and-editor.md`

## M3 - Editor, UI and crossings - in progress

The editor becomes something you can build a network with, and the model grows
the few things traffic will need underneath it: exact curve-curve intersection,
loops, crossings that form junctions on their own, integer height levels so a
bridge is not a junction, collision detection, lane-aware snapping, a real game
interface with modes, CS2-style drawing modes, bulldoze and replace, road
previews that show the actual road, end caps, and rounded junction corners with
the pavement carried round them.

Absorbs the two debts M2 left: exact curve-curve junction intersection in place
of the straight-ray approximation and its trim cap, and splitting a road where a
new one *crosses* it. Both turned out to be the foundation under crossings,
collision detection and junction corners rather than separate errands.

Answers: *what does it take to draw a network the way a player expects to, on a
model that still holds when traffic lands?*

Design: `docs/milestone-3-editor-and-ui.md`

## M4 - Textures & markings

Textured ribbons using the `s` coordinate ribbons already carry. Lane markings
derived from adjacent `LaneSpec` pairs - dashed between same-direction lanes,
solid centre between opposing, kerbs at the outer edges. Junction surface
texturing. Rail sleepers, tram grooves, level crossings.

Answers: *how do you texture all of this, and how do rail and tram lines sit in
a road surface.*

## M5 - Traffic

Derived lane graph, lane-to-lane connections inside junctions (stored - they
carry user intent), vehicles following lanes, then road rules one at a time:
priority, give-way, signals. Pedestrians and crossings after that.

Answers: *vehicles, people, and road rules.*

## Beyond

Whatever survives to here is the model that gets ported to 3D. The test suite
and `docs/decisions.md` are the handover document for that port.
