# Road marking provenance

The polygon rings in `src/roadsim/road/decal_library.py` are converted from
Hong Kong TPDM road-marking drawings.

## Source

- **Repository:** <https://github.com/Lecberg/hk-tpdm-traffic-signs-markings>
- **Site:** <https://lecberg.github.io/hk-tpdm-traffic-signs-markings/>
- **Commit converted from:** `dd775886027a866021400f5e3e4527d0e7c372b7`
- **Files:** `svgs/RM_*.svg`
- **Converted by:** `tools/import_markings.py` (offline; nothing at runtime
  reads SVG)

## Licensing - read before adding more

**That repository carries no LICENSE file**, and the drawings derive from the
Hong Kong Transport Department's *Transport Planning and Design Manual*, which
is a government standard with its own copyright. The upstream README describes
the files as "provided for reference and drafting convenience" and tells you to
verify against the current TPDM before using them in a works submission.

So the position this repo takes is deliberately narrow:

- only the eight markings actually used are converted, not the 1327-entry
  catalogue;
- what ships is a derived polygon outline, not the source SVG;
- the source is recorded here by URL and commit so the provenance is traceable.

If these markings are ever to be used somewhere the licence matters - a
published build, anything commercial - **clear it first.** Treat the shapes as
placeholders standing in for whatever standard that build is entitled to use.

## What was imported, and how it was identified

The catalogue lists codes only, with **no names**, so the mapping was made by
rendering every `RM_*.svg` to a contact sheet and reading it. That is a manual
judgement, recorded here so it can be checked rather than trusted:

| Code      | Name in game           | Read as                                    |
| --------- | ---------------------- | ------------------------------------------ |
| `RM_1167` | `arrow_straight`       | straight-ahead lane arrow                   |
| `RM_1168` | `arrow_right`          | right-turn-only lane arrow                  |
| `RM_1169` | `arrow_left`           | left-turn-only lane arrow                   |
| `RM_1125` | `arrow_straight_left`  | straight-ahead with a left-turn branch      |
| `RM_1148` | `arrow_straight_right` | straight-ahead with a right-turn branch     |
| `RM_1122` | `arrow_merge_left`     | lane-change arrow, path joining to the left  |
| `RM_1123` | `arrow_merge_right`    | lane-change arrow, path joining to the right |
| `RM_1178` | `gore_hatch`           | hatched taper for a gore / lane transition   |

The two merge arrows are the least certain of the eight: both show two heads
with a diagonal tail, and they were assigned by which side the tail joins from.
If they turn out to mean something more specific in the TPDM, the fix is one
line in `CURATED` and a re-run of the importer.

## Re-running the conversion

```bash
uv run python tools/import_markings.py --source <dir of RM_*.svg>
```

It rewrites `src/roadsim/road/decal_library.py` in full. Shapes come out
normalised - centred, +y along travel, exactly 1.0 long - so the real size
stays in `config.py` rather than being baked in at whatever scale the source
sheet happened to use.
