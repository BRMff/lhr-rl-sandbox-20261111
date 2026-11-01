"""Command-line entry point; stdout only."""

from __future__ import annotations

import argparse
from collections.abc import Sequence

from . import __version__
from .collectors import collect_snapshot, has_unavailable
from .renderers import render_json, render_markdown


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="linux-health-reporter",
        description="Read-only Linux health snapshot without identifiers or network requests.",
    )
    parser.add_argument(
        "--format",
        choices=("json", "markdown"),
        default="json",
        help="Output format (default: json). JSON is the stable structured interface.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    args = parser.parse_args(argv)
    snapshot = collect_snapshot()
    print(render_json(snapshot) if args.format == "json" else render_markdown(snapshot))
    return 1 if has_unavailable(snapshot) else 0


if __name__ == "__main__":
    raise SystemExit(main())
