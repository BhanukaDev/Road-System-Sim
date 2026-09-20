# M2 - Network & Editor

**Goal:** draw and edit a road network with real lane cross-sections, see
junctions form where roads meet, and save/load it. Lanes render as flat colored
polygons - textures are M3.

**Prerequisite:** M1 geometry kernel (done). Read `CLAUDE.md` and
`docs/decisions.md` first; D3, D4 and D5 constrain most of what follows.

---

## Build order

Each step should leave the app runnable. Do not build the editor before the
model is right.

1. ~~`road/lane.py`, `road/profile.py` + tests, + profile presets~~ **done** -
   presets landed in `road/presets.py` as data rather than `data/profiles/*.json`,
   because the JSON loader is step 5; moving them out is a loader, not a rewrite
2. ~~`road/node.py`, `road/segment.py`, `road/network.py` + tests~~ **done**
3. ~~`render/lane_style.py`, `render/network_renderer.py`, and a scene that draws
   a **hardcoded** network~~ **done** - `scenes/network_demo.py`
4. ~~`road/junction.py` + trimming, wired into `network.rebuild_dirty()`~~ **done**
5. ~~`serialization/` + round-trip tests~~ **done**
6. ~~`editor/commands.py` + history, then `editor/tool.py` / `toolbox.py` /
   `snapping.py`, then the tools one at a time~~ **done**
7. ~~`scenes/editor.py`, made the default scene~~ **done**

**All seven done.** Two deviations from this design, both deliberate:

- `render/editor_overlay.py` is `editor/overlay.py`, and `Tool.draw_preview`
  is `Tool.preview() -> ToolPreview`. See D8 - the layering here was circular as
  written, and the fix makes every tool testable without a window.
- pair trim demand is capped (see the junction section below).

---

## road/lane.py

```python
class LaneType(Enum):
    CAR, BUS, BIKE, TRAM, RAIL, PARKING, SIDEWALK, MEDIAN, SHOULDER

class Direction(Enum):
    FORWARD, BACKWARD, BOTH, NONE   # relative to the segment's A -> B direction

@dataclass(frozen=True)
class LaneSpec:
    width: float
    direction: Direction
    type: LaneType
    speed_limit: float | None = None
```

Put `carries_vehicles` / `carries_pedestrians` on `LaneType` as properties - M4
will ask, and the answer belongs with the type, not in a table somewhere.

**No colors here.** The LaneType-to-color mapping lives in
`render/lane_style.py`; `road/` must stay importable without pygame (rule 1).

## road/profile.py

```python
@dataclass(frozen=True)
class RoadProfile:
    name: str
    lanes: tuple[LaneSpec, ...]   # ordered LEFT to RIGHT of the A->B direction
    datum: float = 0.0            # lateral shift of the whole profile, +left
```

Derived, never stored (D4): `total_width`, `is_oneway`, `forward_lanes`,
`backward_lanes`.

Offset maths - get this right and the rest of the milestone is downhill:

```
left_edge   = datum + total_width / 2
edges[k]    = left_edge - sum(width of lanes 0..k-1)     # descending, k = 0..n
lane_bounds(k) -> (edges[k], edges[k+1])                 # left, right
lane_center(k) -> (edges[k] + edges[k+1]) / 2
extent_left  =  edges[0]          # for junction trimming
extent_right = -edges[-1]
```

Offsets **decrease** left to right, because `offset(+d)` shifts left (D3).

Presets to ship in `data/profiles/` - these are the brief's cases and double as
the visual test set:

| file | lanes |
|---|---|
| `residential_two_way` | sidewalk, car BACK, car FWD, sidewalk |
| `one_way_two_lane` | sidewalk, car FWD, car FWD, sidewalk |
| `asymmetric_boulevard` | sidewalk, car BACK, median, car FWD, car FWD, sidewalk |
| `tram_avenue` | sidewalk, car BACK, tram BOTH, car FWD, sidewalk |
| `rail_double` | shoulder, rail BACK, rail FWD, shoulder |

## road/node.py and road/segment.py

```python
@dataclass
class RoadNode:
    id: int
    position: Vec2

@dataclass
class RoadSegment:
    id: int
    node_a: int
    node_b: int
    control_points: list[Vec2]   # AUTHORITATIVE. [0] and [-1] are the nodes.
    corner_radius: float
    profile: RoadProfile
    # derived, refreshed by rebuild:
    path: Path
    trim_a: float = 0.0
    trim_b: float = 0.0
```

**`control_points` is the source of truth; `path` is derived** via
`fit_polyline(control_points, corner_radius)`. This matters in three places:

- moving a node = update `control_points[0]` or `[-1]` and refit
- serialization stores control points, never the fitted path (D5's principle,
  applied to segments)
- changing `corner_radius` later just refits

Derived accessors:

- `carriageway_path` gives `path.shortened(trim_a, trim_b)`
- `lane_ribbon(k, tolerance)` gives
  `build_ribbon(path, *profile.lane_bounds(k), tolerance, s0=trim_a, s1=path.length - trim_b)`
- `is_too_short` when `trim_a + trim_b >= path.length - MIN_CARRIAGEWAY`

**Handle `is_too_short`.** Two junctions closer together than their combined
trim is a case the user *will* hit within a minute of drawing. Do not let
`Path.trimmed` raise into the render loop: flag the segment, skip its
carriageway, and draw it red in the editor overlay.

## road/junction.py (D5: derived, never stored)

Rebuild for any node with 2+ segment ends:

1. Collect each end as `(segment_id, at_a, outgoing_dir, extent_left, extent_right)`.
   `outgoing_dir` is the path tangent at that end, pointing **away** from the
   node. When the end is `node_b`, the tangent flips *and so do left/right* -
   getting this backwards is the most likely bug in the milestone, so test it
   explicitly with an asymmetric profile.
2. Sort ends by `outgoing_dir.angle` (CCW).
3. For each adjacent pair `(A, B)` in that order, intersect A's **left** edge
   with B's **right** edge. The distance from the node to that intersection,
   along each segment, is what that pair demands.
4. `trim` is the max demand over all pairs the end appears in, floored at the
   segment's own half-width so a junction is never narrower than its roads.
5. Junction polygon: walk the ends in CCW order, taking each trimmed end's two
   cross-section corners, joining consecutive ends corner-to-corner.

**Approximation for M2:** intersect the straight *tangent rays* at the node
rather than the real curves. Roads are near-straight at their ends anyway -
fillet clamping caps each corner at half its straight, so every segment keeps
some straight run at each end. Exact curve-curve intersection is M3. Leave a
comment saying so.

**The cap this needs (found while building the editor).** As two arms approach
collinear their kerbs approach parallel, so the crossing point runs off toward
infinity: drag a node until two roads leave at a shallow angle and the junction
inflates until it swallows the roads feeding it. Exactly parallel is already
handled (no intersection); *nearly* parallel is the dangerous case. Each pair
demand is therefore capped at `JUNCTION_MAX_TRIM_FACTOR` times the widest arm's
half-width, which leaves a shallow corner blunt instead of infinite. M3's corner
fillets retire the cap along with the approximation it patches.

Cases to handle: dead end (1 end, no trim, flat cap); 2 ends with the same
profile (no junction, roads simply meet); 2 ends with different profiles (M2:
trim both, draw the junction polygon as a transition patch).

## road/network.py

```python
class RoadNetwork:
    nodes: dict[int, RoadNode]
    segments: dict[int, RoadSegment]
    junctions: dict[int, Junction]   # keyed by node id, derived
```

Mutators, each marking touched nodes dirty: `add_node`, `add_segment`,
`remove_segment`, `remove_node`, `move_node`, `set_profile`, `split_segment`.

`split_segment(id, s)` inserts a node at arc length `s` and replaces the segment
with two - this is what a T-junction *is* when you draw onto an existing road.
Splitting control points is fiddly: split the fitted path at `s`, then take each
half's flattened corner points as the new control points. Accept a small shape
change at the split; do not try to preserve the original fillets.

`rebuild_dirty()` recomputes junctions for dirty nodes, then trims for every
segment touching them. Call it once per frame after commands, never mid-command.

## serialization/

`schema.py` (versioned dict to/from objects) plus `io.py` (JSON). Store **only**
authoritative state - control points, radius, profile name, node positions and
ids. Never paths, trims or junctions (D5).

```json
{
  "version": 1,
  "profiles": { "tram_avenue": { "datum": 0.0, "lanes": [] } },
  "nodes": [{ "id": 1, "x": -40.0, "y": 0.0 }],
  "segments": [{ "id": 1, "a": 1, "b": 2, "profile": "tram_avenue",
                 "radius": 12.0, "points": [[-40, 0], [10, 25], [60, 0]] }]
}
```

Test: build a network, save, load, save again - the two JSON payloads must be
byte-identical.

## editor/

**`commands.py`** - a `Command` ABC with `do(network)` / `undo(network)` and a
`label`; a `History` with undo/redo stacks. Concrete commands: `AddSegment`,
`RemoveSegment`, `MoveNode`, `SetProfile`, `SplitSegment`. Nothing else may
mutate the network (rule 3).

**`snapping.py`** - returns a `Snap(kind, position, payload)`:

| kind | payload | meaning |
|---|---|---|
| `NODE` | node id | connect to an existing node |
| `SEGMENT` | (segment id, s) | split there and connect |
| `GRID` | - | free point on the grid |
| `ANGLE` | - | constrained to 15 deg from the last point (hold Shift) |

Snap radii are in **pixels**, converted via `camera.zoom` - a snap that gets
harder to hit as you zoom out is a snap that is broken.

**`tool.py` / `toolbox.py`** - a `Tool` ABC (`activate`, `deactivate`,
`handle_event`, `update`, `draw_preview`, `hud_lines`) and a registry with
number-key hotkeys. Adding a tool is one file plus one registry line (rule 2).

**Tools:**

- `DrawRoadTool` - click to place control points, drag for freehand
  (`fit_freehand`), live preview of the fitted path with the active profile,
  Enter or right-click to commit as one `AddSegment`, Esc to cancel. Snapping at
  both ends; a `SEGMENT` snap commits a `SplitSegment` first.
- `SelectTool` - pick a segment or node, show its details in the HUD.
- `MoveNodeTool` - drag a node, refit live, rebuild junctions live.
- `ProfileTool` - cycle the active profile, apply it to the clicked segment.

## render/

- `lane_style.py` - LaneType to `(fill, edge, layer)`. The only place lane
  colors exist.
- `network_renderer.py` - lane ribbons bottom-up by layer, then junction
  polygons, then direction arrows along each traffic lane's centre (spaced by
  arc length - the ribbon already carries `s`).
- `editor_overlay.py` - nodes, control points, selection highlight, snap
  indicator, tool preview, too-short segments in red.

Both take `camera.world_tolerance`. Neither mutates anything (rule 1).

## scenes/editor.py

Owns the network, toolbox, history and renderers. Register it in
`scenes/__init__.py` and make it `DEFAULT_SCENE`; keep `debug` reachable via
`--scene debug`.

Keybindings: `1..9` tools, `Ctrl+Z` / `Ctrl+Shift+Z` undo/redo, `Ctrl+S` /
`Ctrl+O` save/load, `Tab` cycle profile, `Delete` remove selection, `F2` toggle
debug overlays.

---

## Tests to write

Geometry stays at `EXACT = 1e-9`; topology tests assert structure.

- **profile** - edges descend left to right; `total_width` is the sum; datum
  shifts every edge equally without changing widths; asymmetric profiles put
  more width on the intended side; `is_oneway` is derived correctly; each
  shipped preset loads and has sane extents.
- **segment** - path is refit from control points; moving an endpoint moves the
  path end exactly there; lane ribbons land on `profile.lane_bounds(k)` to
  `EXACT`; `is_too_short` trips instead of raising.
- **network** - add/remove keeps ids stable; `remove_node` removes its
  segments; `split_segment` preserves total length within fitting tolerance and
  leaves both halves connected to the new node; dirty tracking marks exactly the
  touched nodes.
- **junction** - a 4-way crossing trims all four ends by more than zero; a wider
  road forces a larger trim on the road it crosses; a dead end trims nothing; a
  straight-through node with one profile creates no junction; **an asymmetric
  profile trims correctly from both the `node_a` and `node_b` end** (the
  left/right flip in step 1).
- **commands** - every command `do` then `undo` restores a byte-identical
  serialized payload; redo reapplies it.
- **serialization** - round-trip is byte-identical; an unknown `version` is
  rejected with a clear error.

## Done when

You can draw a tram avenue, draw a residential road across it, watch the
junction form, drag a node and see it rebuild live, undo the lot, redo it, save,
quit, reload, and get the same network back - with `uv run pytest` green.
