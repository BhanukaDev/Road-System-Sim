# Roadmap

Each milestone answers a question from the original brief. Nothing moves on
until the previous answer holds up visually *and* under test.

## M0 - Scaffolding — done

Window, camera (pan/zoom, adaptive grid), HUD, scene registry, `uv` project.

## M1 - Geometry kernel — done

`Curve` / `LineSegment` / `ArcSegment` / `Path`, tangent-arc-tangent fitting,
freehand stroke fitting, ribbons. Plus the `debug` scene that makes failures
visible and 101 tests that make them precise.

Answers: *how do you draw organic roads, and how do you get exact lane offsets?*

## M2 - Network + editor — next

`road/` topology, lane profiles, derived junctions, the `Tool`/`Command`
framework with undo, JSON save/load. Lanes render as flat colored polygons.

Answers: *two-way, one-way, asymmetric, tram and rail cross-sections; what
happens where roads meet.*

Design: `docs/milestone-2-network-and-editor.md`

## M3 - Textures & markings � next

Textured ribbons using the `s` coordinate ribbons already carry. Lane markings
derived from adjacent `LaneSpec` pairs - dashed between same-direction lanes,
solid centre between opposing, kerbs at the outer edges. Junction surface
texturing and proper corner fillets. Rail sleepers, tram grooves, level
crossings.

Also: replace M2's straight-ray junction trimming with exact curve-curve
intersection - which also retires the shallow-angle trim cap and lets a road
split another where it *crosses* it, not just where it ends on it.

Answers: *how do you texture all of this, and how do rail and tram lines sit in
a road surface.*

## M4 - Traffic

Derived lane graph, lane-to-lane connections inside junctions (stored - they
carry user intent), vehicles following lanes, then road rules one at a time:
priority, give-way, signals. Pedestrians and crossings after that.

Answers: *vehicles, people, and road rules.*

## Beyond

Whatever survives to here is the model that gets ported to 3D. The test suite
and `docs/decisions.md` are the handover document for that port.
