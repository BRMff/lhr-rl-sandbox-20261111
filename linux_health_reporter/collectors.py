"""Read-only Linux collectors. No shell, network, host identifiers or writes."""

from __future__ import annotations

from datetime import datetime, timezone
import math
import os
from pathlib import Path
import re
from typing import Callable


METRIC_FIELDS = {
    "load_average": ("1m", "5m", "15m"),
    "memory": ("total_bytes", "available_bytes"),
    "disk_root": ("total_bytes", "available_bytes"),
    "uptime": ("uptime_seconds",),
}


def _unavailable(fields: tuple[str, ...]) -> dict:
    return {"status": "unavailable", **{field: None for field in fields}}


def _ok(**values: int | float) -> dict:
    return {"status": "ok", **values}


def parse_loadavg(text: str) -> dict:
    fields = text.split()
    if len(fields) < 3:
        raise ValueError("missing load averages")
    values = [float(value) for value in fields[:3]]
    if any(not math.isfinite(value) or value < 0 for value in values):
        raise ValueError("invalid load averages")
    return _ok(**dict(zip(METRIC_FIELDS["load_average"], values)))


def parse_meminfo(text: str) -> dict:
    values: dict[str, int] = {}
    wanted = {"MemTotal": "total_bytes", "MemAvailable": "available_bytes"}
    for line in text.splitlines():
        key, separator, raw = line.partition(":")
        if not separator or key not in wanted:
            continue
        if key in values:
            raise ValueError("duplicate memory field")
        match = re.fullmatch(r"\s*(\d+)\s+kB\s*", raw)
        if match is None:
            raise ValueError("invalid memory field")
        values[key] = int(match.group(1)) * 1024
    if len(values) != 2:
        raise ValueError("missing memory fields")
    total = values["MemTotal"]
    available = values["MemAvailable"]
    if total <= 0 or available > total:
        raise ValueError("inconsistent memory values")
    return _ok(total_bytes=total, available_bytes=available)


def parse_uptime(text: str) -> dict:
    fields = text.split()
    if not fields:
        raise ValueError("missing uptime")
    uptime = float(fields[0])
    if not math.isfinite(uptime) or uptime < 0:
        raise ValueError("invalid uptime")
    return _ok(uptime_seconds=int(uptime))


def parse_disk_statvfs(result: os.statvfs_result) -> dict:
    fragment_size = int(result.f_frsize)
    total_blocks = int(result.f_blocks)
    available_blocks = int(result.f_bavail)
    if fragment_size <= 0 or total_blocks <= 0:
        raise ValueError("invalid filesystem size")
    if not (0 <= available_blocks <= total_blocks):
        raise ValueError("invalid available blocks")
    return _ok(
        total_bytes=total_blocks * fragment_size,
        available_bytes=available_blocks * fragment_size,
    )


def _read_proc(path: str) -> str:
    return Path(path).read_text(encoding="ascii")


def _safe_read(
    path: str,
    parser: Callable[[str], dict],
    fields: tuple[str, ...],
    read_text: Callable[[str], str],
) -> dict:
    try:
        return parser(read_text(path))
    except (OSError, ValueError, TypeError, OverflowError, UnicodeError):
        # Do not expose paths or raw exception messages in public reports.
        return _unavailable(fields)


def _safe_disk(statvfs: Callable[[str], os.statvfs_result]) -> dict:
    try:
        return parse_disk_statvfs(statvfs("/"))
    except (OSError, ValueError, TypeError, OverflowError):
        return _unavailable(METRIC_FIELDS["disk_root"])


def _timestamp(clock: Callable[[], datetime]) -> str | None:
    try:
        value = clock()
        if value.tzinfo is None or value.utcoffset() is None:
            return None
        return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace(
            "+00:00", "Z"
        )
    except (AttributeError, TypeError, ValueError, OverflowError, OSError):
        # A clock failure must not abort an otherwise usable health snapshot.
        return None


def collect_snapshot(
    *,
    read_text: Callable[[str], str] = _read_proc,
    statvfs: Callable[[str], os.statvfs_result] = os.statvfs,
    clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
) -> dict:
    """Collect fixed, non-identifying metrics. Dependencies can be injected for tests."""
    return {
        "schema_version": "0.1",
        "timestamp_utc": _timestamp(clock),
        "load_average": _safe_read(
            "/proc/loadavg", parse_loadavg, METRIC_FIELDS["load_average"], read_text
        ),
        "memory": _safe_read(
            "/proc/meminfo", parse_meminfo, METRIC_FIELDS["memory"], read_text
        ),
        "disk_root": _safe_disk(statvfs),
        "uptime": _safe_read(
            "/proc/uptime", parse_uptime, METRIC_FIELDS["uptime"], read_text
        ),
    }


def has_unavailable(snapshot: dict) -> bool:
    # The timestamp is missing if it is None or an empty string.
    return not snapshot.get("timestamp_utc") or any(
        snapshot.get(metric, {}).get("status") != "ok" for metric in METRIC_FIELDS
    )
