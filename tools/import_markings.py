"""Convert TPDM road-marking SVGs into world-space polygon rings.

Run by hand, not by the app - it writes `src/roadsim/road/decal_library.py`,
which is what ships. Nothing at runtime parses SVG, so the game keeps its single
dependency and a decal stays exact at any zoom instead of resampling the way a
sprite would. The rings are plain polygons, so they port to a 3D engine as
meshes rather than as textures.

    uv run python tools/import_markings.py --source <dir of RM_*.svg>

Only the markings in `CURATED` are converted. The catalogue is codes-only with
no names, so the mapping below was built by rendering the candidates and
reading them; see `assets/markings/ATTRIBUTION.md` for provenance.

Shapes are normalised, not scaled to metres: each one is centred on the origin
with +y pointing the way traffic travels and its length scaled to 1.0. The real
size is `config.TURN_ARROW_LENGTH` and friends at draw time, which keeps the
number in `config.py` where every other tunable lives (rule 4) rather than
baked into generated data by whatever scale the source sheet happened to use.
"""

from __future__ import annotations

import argparse
import re
import xml.etree.ElementTree as ET
from pathlib import Path

CURATED: dict[str, str] = {
    "RM_1167": "arrow_straight",
    "RM_1168": "arrow_right",
    "RM_1169": "arrow_left",
    "RM_1125": "arrow_straight_left",
    "RM_1148": "arrow_straight_right",
    "RM_1021": "arrow_merge_right",
    "RM_1178": "gore_hatch",
    "RM_1029": "arrow_straight_left_right",
}
"""Source code -> the name the game knows it by.

`arrow_merge_left` is not in here: it is `RM_1019`, a left-right mirror of
`RM_1021` with nothing else different, so `road/decal.py` derives it from
`arrow_merge_right` by negating x rather than carrying two near-duplicate
polygons - the same "use one and flip" call this file makes for handedness
everywhere else."""

SVG_NS = "{http://www.w3.org/2000/svg}"

FLATTEN_TOLERANCE = 1e-3
"""In source units, against shapes about 30 units tall - fine enough that
normalising to unit length leaves no visible facet."""

Matrix = tuple[float, float, float, float, float, float]
IDENTITY: Matrix = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)
"""SVG's own `(a, b, c, d, e, f)`, laid out as [a c e; b d f]."""


# -- transforms -------------------------------------------------------------


def compose(m: Matrix, n: Matrix) -> Matrix:
    a, b, c, d, e, f = m
    a2, b2, c2, d2, e2, f2 = n
    return (
        a * a2 + c * b2,
        b * a2 + d * b2,
        a * c2 + c * d2,
        b * c2 + d * d2,
        a * e2 + c * f2 + e,
        b * e2 + d * f2 + f,
    )


def apply(m: Matrix, x: float, y: float) -> tuple[float, float]:
    a, b, c, d, e, f = m
    return a * x + c * y + e, b * x + d * y + f


def parse_transform(text: str | None) -> Matrix:
    """The subset these files use: `matrix`, `translate`, `scale`.

    Listed transforms apply right to left - the rightmost acts on the point
    first - which is the order `compose` folds them in.
    """
    if not text:
        return IDENTITY
    out = IDENTITY
    for name, args in re.findall(r"(\w+)\s*\(([^)]*)\)", text):
        values = [float(v) for v in re.split(r"[\s,]+", args.strip()) if v]
        if name == "matrix" and len(values) == 6:
            step: Matrix = (
                values[0],
                values[1],
                values[2],
                values[3],
                values[4],
                values[5],
            )
        elif name == "translate" and values:
            ty = values[1] if len(values) > 1 else 0.0
            step = (1.0, 0.0, 0.0, 1.0, values[0], ty)
        elif name == "scale" and values:
            sy = values[1] if len(values) > 1 else values[0]
            step = (values[0], 0.0, 0.0, sy, 0.0, 0.0)
        else:
            raise ValueError(f"unsupported transform {name!r} in {text!r}")
        out = compose(out, step)
    return out


# -- path data --------------------------------------------------------------

_TOKEN = re.compile(r"([MmLlHhVvCcQqSsTtZz])|(-?\d*\.?\d+(?:[eE][-+]?\d+)?)")


class _Reader:
    """A cursor over one `d` attribute's tokens."""

    def __init__(self, d: str) -> None:
        self.tokens = [(cmd or num) for cmd, num in _TOKEN.findall(d)]
        self.i = 0

    def done(self) -> bool:
        return self.i >= len(self.tokens)

    def peek_command(self) -> str | None:
        token = self.tokens[self.i]
        return token if token.isalpha() else None

    def take(self) -> str:
        token = self.tokens[self.i]
        self.i += 1
        return token

    def number(self) -> float:
        return float(self.take())


def parse_path(d: str) -> list[list[tuple[float, float]]]:
    """`d` as a list of closed rings, curves flattened.

    Elliptical arcs (`A`) are refused rather than approximated: nothing in the
    curated set uses one, and a guessed shape is worse than a stop.
    """
    reader = _Reader(d)
    rings: list[list[tuple[float, float]]] = []
    ring: list[tuple[float, float]] = []
    cursor = (0.0, 0.0)
    start = (0.0, 0.0)
    command = ""
    control: tuple[float, float] | None = None

    def flush() -> None:
        nonlocal ring
        if len(ring) >= 3:
            rings.append(ring)
        ring = []

    while not reader.done():
        found = reader.peek_command()
        if found is not None:
            command = reader.take()
            if command in "Zz":
                flush()
                cursor = start
                continue
        relative = command.islower()
        op = command.upper()

        def point() -> tuple[float, float]:
            x, y = reader.number(), reader.number()
            return (cursor[0] + x, cursor[1] + y) if relative else (x, y)

        if op == "M":
            cursor = point()
            flush()
            start = cursor
            ring = [cursor]
            command = "l" if relative else "L"
            control = None
        elif op == "L":
            cursor = point()
            ring.append(cursor)
            control = None
        elif op == "H":
            x = reader.number()
            cursor = (cursor[0] + x if relative else x, cursor[1])
            ring.append(cursor)
            control = None
        elif op == "V":
            y = reader.number()
            cursor = (cursor[0], cursor[1] + y if relative else y)
            ring.append(cursor)
            control = None
        elif op in ("C", "S", "Q", "T"):
            if op == "C":
                c1, c2, end = point(), point(), point()
            elif op == "S":
                c1 = _reflect(cursor, control)
                c2, end = point(), point()
            elif op == "Q":
                mid, end = point(), point()
                c1, c2 = _lerp(cursor, mid, 2.0 / 3.0), _lerp(end, mid, 2.0 / 3.0)
            else:
                mid = _reflect(cursor, control)
                end = point()
                c1, c2 = _lerp(cursor, mid, 2.0 / 3.0), _lerp(end, mid, 2.0 / 3.0)
            _flatten_cubic(cursor, c1, c2, end, ring)
            control = c2 if op in ("C", "S") else mid
            cursor = end
        else:
            raise ValueError(f"unsupported path command {command!r}")
    flush()
    return rings


def _reflect(
    current: tuple[float, float], control: tuple[float, float] | None
) -> tuple[float, float]:
    if control is None:
        return current
    return (2.0 * current[0] - control[0], 2.0 * current[1] - control[1])


def _lerp(
    a: tuple[float, float], b: tuple[float, float], t: float
) -> tuple[float, float]:
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)


def _flatten_cubic(p0, p1, p2, p3, out, depth: int = 0) -> None:
    """Recursive subdivision against a flatness measure, so a long sweep gets
    the points it needs and a short one does not pay for them."""
    if depth >= 16 or _flatness(p0, p1, p2, p3) <= FLATTEN_TOLERANCE:
        out.append(p3)
        return
    p01, p12, p23 = _lerp(p0, p1, 0.5), _lerp(p1, p2, 0.5), _lerp(p2, p3, 0.5)
    p012, p123 = _lerp(p01, p12, 0.5), _lerp(p12, p23, 0.5)
    mid = _lerp(p012, p123, 0.5)
    _flatten_cubic(p0, p01, p012, mid, out, depth + 1)
    _flatten_cubic(mid, p123, p23, p3, out, depth + 1)


def _flatness(p0, p1, p2, p3) -> float:
    ux = 3.0 * p1[0] - 2.0 * p0[0] - p3[0]
    uy = 3.0 * p1[1] - 2.0 * p0[1] - p3[1]
    vx = 3.0 * p2[0] - p0[0] - 2.0 * p3[0]
    vy = 3.0 * p2[1] - p0[1] - 2.0 * p3[1]
    return max(ux * ux, vx * vx) + max(uy * uy, vy * vy)


# -- document ---------------------------------------------------------------


def read_rings(path: Path) -> list[list[tuple[float, float]]]:
    root = ET.parse(path).getroot()
    rings: list[list[tuple[float, float]]] = []

    def walk(node: ET.Element, parent: Matrix) -> None:
        if node.tag == f"{SVG_NS}defs":
            return  # a clip path's own geometry is never painted
        here = compose(parent, parse_transform(node.get("transform")))
        if node.tag == f"{SVG_NS}path":
            d = node.get("d")
            if d and node.get("fill") != "none":
                for ring in parse_path(d):
                    rings.append([apply(here, x, y) for x, y in ring])
        for child in node:
            walk(child, here)

    walk(root, IDENTITY)
    if not rings:
        raise ValueError(f"{path.name} has no filled paths")
    return rings


def normalise(
    rings: list[list[tuple[float, float]]],
) -> tuple[list[list[tuple[float, float]]], float]:
    """Centre on the origin, flip to +y up, and scale to unit length.

    SVG is y-down and world space is y-up (D3). The flip belongs here, at the
    edge where foreign data comes in, rather than at draw time: the camera owns
    the only other y flip in the codebase and a second one next to it is how
    handedness bugs start.
    """
    flipped = [[(x, -y) for x, y in ring] for ring in rings]
    xs = [x for ring in flipped for x, _ in ring]
    ys = [y for ring in flipped for _, y in ring]
    cx, cy = (min(xs) + max(xs)) / 2.0, (min(ys) + max(ys)) / 2.0
    length, width = max(ys) - min(ys), max(xs) - min(xs)
    if length <= 0.0:
        raise ValueError("a marking with no length along the direction of travel")
    scale = 1.0 / length
    out = [[((x - cx) * scale, (y - cy) * scale) for x, y in ring] for ring in flipped]
    return out, width / length


HEADER = '''"""Generated by `tools/import_markings.py` - do not edit by hand.

Road-marking outlines from the Hong Kong TPDM library, as polygon rings in a
normalised frame: centred on the origin, +y along the direction of travel, and
exactly 1.0 long. `road/decal.py` wraps these; `config.py` owns the real size.

Provenance and licensing: `assets/markings/ATTRIBUTION.md`.
"""

from __future__ import annotations

RINGS: dict[str, tuple[tuple[tuple[float, float], ...], ...]] = {
'''

ASPECT_DOC = '"""Width as a fraction of length, so a decal keeps its proportions."""'


def main() -> None:
    parser = argparse.ArgumentParser(description="Convert TPDM marking SVGs.")
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument(
        "--out", type=Path, default=Path("src/roadsim/road/decal_library.py")
    )
    args = parser.parse_args()

    entries: list[str] = []
    aspects: list[str] = []
    for code, name in sorted(CURATED.items(), key=lambda kv: kv[1]):
        rings, aspect = normalise(read_rings(args.source / f"{code}.svg"))
        body = ",\n".join(
            "        (" + ", ".join(f"({x:.6f}, {y:.6f})" for x, y in ring) + ",)"
            for ring in rings
        )
        entries.append(f'    "{name}": (  # {code}\n{body},\n    ),')
        aspects.append(f'    "{name}": {aspect:.6f},')
        print(f"{code} -> {name}: {len(rings)} ring(s), aspect {aspect:.3f}")

    text = "".join(
        [
            HEADER,
            "\n".join(entries),
            "\n}\n\nASPECT: dict[str, float] = {\n",
            "\n".join(aspects),
            "\n}\n",
            ASPECT_DOC,
            "\n",
        ]
    )
    args.out.write_text(text, encoding="utf-8")
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
