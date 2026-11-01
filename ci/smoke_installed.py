"""CI helper: exercise the *installed* package with synthetic inputs only.

Run with the virtual environment's interpreter, from outside the source tree,
using ``python -I``. It never reads the runner's /proc or filesystem: every
collector source is injected, so no real host telemetry is collected.
"""

from __future__ import annotations

from datetime import datetime, timezone
import errno
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import linux_health_reporter
from linux_health_reporter.collectors import collect_snapshot, has_unavailable
from linux_health_reporter.renderers import render_json, render_markdown

SOURCES = {
    "/proc/loadavg": "0.42 0.36 0.31 1/160 99\n",
    "/proc/meminfo": "MemTotal: 16384000 kB\nMemAvailable: 9216000 kB\nSwapTotal: 0 kB\nSwapFree: 0 kB\n",
    "/proc/uptime": "86400.84 303.10\n",
    "/proc/pressure/cpu": "some avg10=1.25 avg60=0.80 avg300=0.40 total=1\n",
    "/proc/pressure/memory": "some avg10=0.50 avg60=0.25 avg300=0.10 total=1\nfull avg10=0.20 avg60=0.10 avg300=0.05 total=1\n",
}


def reader(path: str) -> str:
    if path in SOURCES:
        return SOURCES[path]
    if path == "/proc/pressure/io":
        raise FileNotFoundError(errno.ENOENT, "synthetic: interface not exposed")
    raise AssertionError(f"unexpected read: {path}")


def main() -> int:
    module_path = Path(linux_health_reporter.__file__).resolve()
    if not module_path.is_relative_to(Path(sys.prefix).resolve()):
        print(f"package not imported from the environment: {module_path}", file=sys.stderr)
        return 1

    snapshot = collect_snapshot(
        read_text=reader,
        statvfs=lambda path: SimpleNamespace(f_frsize=4096, f_blocks=100, f_bavail=50),
        clock=lambda: datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc),
    )
    parsed = json.loads(render_json(snapshot))
    checks = {
        "schema version": parsed["schema_version"] == "0.2",
        "v0.1 keys first": list(parsed)[:6]
        == ["schema_version", "timestamp_utc", "load_average", "memory", "disk_root", "uptime"],
        "swap ok without swap": parsed["swap"] == {"status": "ok", "total_bytes": 0, "free_bytes": 0},
        "io unsupported": parsed["pressure"]["io"]["status"] == "unsupported",
        "unsupported is not a failure": not has_unavailable(snapshot),
        "markdown renders": "Not supported by kernel" in render_markdown(snapshot),
    }
    failed = [name for name, ok in checks.items() if not ok]
    if failed:
        print(f"smoke checks failed: {failed}", file=sys.stderr)
        return 1
    print(f"installed package OK ({len(checks)} synthetic checks)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
