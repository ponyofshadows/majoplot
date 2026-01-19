from __future__ import annotations

import argparse

from .app.cli import run_cli
from .app.gui import run_gui


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="majoplot")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--gui", "-g", action="store_true", help="Launch GUI (default)")
    group.add_argument("--cli", "-c", action="store_true", help="Launch CLI")
    args, _ = parser.parse_known_args(argv)

    if args.cli:
        run_cli()
        return

    # default GUI (also for --gui/-g)
    run_gui()


if __name__ == "__main__":
    main()
