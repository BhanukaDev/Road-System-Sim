"""Entry point: `uv run road-sim [--scene NAME]`."""

from __future__ import annotations

import argparse

from .app import App
from .scenes import DEFAULT_SCENE, SCENES


def main() -> None:
    parser = argparse.ArgumentParser(prog="road-sim")
    parser.add_argument(
        "--scene",
        default=DEFAULT_SCENE,
        choices=sorted(SCENES),
        help="which scene to start in",
    )
    args = parser.parse_args()
    App(args.scene).run()


if __name__ == "__main__":
    main()
