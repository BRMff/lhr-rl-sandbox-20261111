"""Read-only Linux collectors. No shell, network, host identifiers or writes."""

from __future__ import annotations

from datetime import datetime, timezone
import errno
import math
import os
from pathlib import Path
import re
from typing import Callable


SCHEMA_VERSION = "0.2"

# Status values. "unsupported" is reserved for PSI blocks whose kernel
# interface is not exposed; every other failure is "unavailable".
STATUS_OK = "ok"
STATUS_UNAVAILABLE = "unavailable"
STATUS_UNSUPPORTED = "unsupported"

METRIC_FIELDS = {
    "load_average": ("1m", "5m", "15m"),
    "memory": ("total_bytes", "available_bytes"),
    "disk_root": ("total_bytes", "available_bytes"),
    "uptime": ("uptime_seconds",),
    "swap": ("total_bytes", "free_bytes"),
}

# PSI resources and the stall lines reported for each. The system-wide CPU
# "full" line is undefined (always zero) and is deliberately not reported.
PRESSURE_LINES = {
    "cpu": ("some",),
    "memory": ("some", "full"),
    "io": ("some", "full"),
}
PRESSURE_WINDOWS = ("avg10", "avg60", "avg300")

# Exactly the sources the collector may read. /proc/swaps is excluded on
# purpose: it exposes device names and swap-file paths.
PROC_SOURCES = (
    "/proc/loadavg",
    "/proc/meminfo",
    "/proc/uptime",
    "/proc/pressure/cpu",
    "/proc/pressure/memory",
    "/proc/pressure/io",
)

# errno values meaning "this kernel interface is not exposed here".
_NOT_EXPOSED = {errno.ENOENT, errno.EOPNOTSUPP, getattr(errno, "ENOTSUP", errno.EOPNOTSUPP)}

_COLLECTION_ERRORS = (OSError, ValueError, TypeError, OverflowError, UnicodeError)


def _unavailable(fields: tuple[str, ...]) -> dict:
    return {"status": STATUS_UNAVAILABLE, **{field: None for field in fields}}


def _ok(**values: int | float) -> dict:
    return {"status": STATUS_OK, **values}


def parse_loadavg(text: str) -> dict:
    fields = text.split()
    if len(fields) < 3:
        raise ValueError("missing load averages")
    values = [float(value) for value in fields[:3]]
    if any(not math.isfinite(value) or value < 0 for value in values):
        raise ValueError("invalid load averages")
    return _ok(**dict(zip(METRIC_FIELDS["load_average"], values)))


def _meminfo_bytes(text: str, wanted: tuple[str, ...]) -> dict[str, int]:
    """Return the wanted /proc/meminfo fields in bytes; other lines are ignored."""
    values: dict[str, int] = {}
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
    if len(values) != len(wanted):
        raise ValueError("missing memory fields")
    return values


def parse_meminfo(text: str) -> dict:
    values = _meminfo_bytes(text, ("MemTotal", "MemAvailable"))
    total = values["MemTotal"]
    available = values["MemAvailable"]
    if total <= 0 or available > total:
        raise ValueError("inconsistent memory values")
    return _ok(total_bytes=total, available_bytes=available)


def parse_swap(text: str) -> dict:
    """Swap totals from /proc/meminfo. A system without swap is valid (0/0)."""
    values = _meminfo_bytes(text, ("SwapTotal", "SwapFree"))
    total = values["SwapTotal"]
    free = values["SwapFree"]
    if free > total:
        raise ValueError("inconsistent swap values")
    return _ok(total_bytes=total, free_bytes=free)


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


def _parse_pressure_line(fields: list[str]) -> dict:
    averages: dict[str, float] = {}
    for token in fields:
        key, separator, raw = token.partition("=")
        if not separator or not key:
            raise ValueError("malformed pressure field")
        if key not in PRESSURE_WINDOWS:
            continue  # e.g. "total": cumulative counter, not reported
        if key in averages:
            raise ValueError("duplicate pressure field")
        value = float(raw)
        if not math.isfinite(value) or not 0 <= value <= 100:
            raise ValueError("invalid pressure value")
        averages[key] = value
    if len(averages) != len(PRESSURE_WINDOWS):
        raise ValueError("missing pressure averages")
    return {window: averages[window] for window in PRESSURE_WINDOWS}


def parse_pressure(text: str, resource: str) -> dict:
    """Parse one /proc/pressure/<resource> file into fixed PSI windows."""
    expected = PRESSURE_LINES[resource]
    lines: dict[str, dict] = {}
    for line in text.splitlines():
        fields = line.split()
        if not fields:
            continue
        kind = fields[0]
        if kind not in expected:
            # Unknown line kinds and lines not reported for this resource
            # (the system-wide CPU "full" line) are skipped before validation,
            # so they can never affect the reported lines.
            continue
        if kind in lines:
            raise ValueError("duplicate pressure line")
        lines[kind] = _parse_pressure_line(fields[1:])
    if any(kind not in lines for kind in expected):
        raise ValueError("missing pressure line")
    return {"status": STATUS_OK, **{kind: lines[kind] for kind in expected}}


def _pressure_placeholder(resource: str, status: str) -> dict:
    return {"status": status, **{kind: None for kind in PRESSURE_LINES[resource]}}


def _read_proc(path: str) -> str:
    return Path(path).read_text(encoding="ascii")


def _safe_text(path: str, read_text: Callable[[str], str]) -> str | None:
    try:
        return read_text(path)
    except _COLLECTION_ERRORS:
        return None


def _safe_parse(text: str | None, parser: Callable[[str], dict], fields: tuple[str, ...]) -> dict:
    if text is None:
        return _unavailable(fields)
    try:
        return parser(text)
    except _COLLECTION_ERRORS:
        # Do not expose paths or raw exception messages in public reports.
        return _unavailable(fields)


def _safe_disk(statvfs: Callable[[str], os.statvfs_result]) -> dict:
    try:
        return parse_disk_statvfs(statvfs("/"))
    except (OSError, ValueError, TypeError, OverflowError):
        return _unavailable(METRIC_FIELDS["disk_root"])


def _safe_pressure(resource: str, read_text: Callable[[str], str]) -> dict:
    try:
        text = read_text("/proc/pressure/" + resource)
    except OSError as exc:
        if exc.errno in _NOT_EXPOSED and not isinstance(exc, PermissionError):
            return _pressure_placeholder(resource, STATUS_UNSUPPORTED)
        return _pressure_placeholder(resource, STATUS_UNAVAILABLE)
    except (ValueError, TypeError, OverflowError, UnicodeError):
        return _pressure_placeholder(resource, STATUS_UNAVAILABLE)
    try:
        return parse_pressure(text, resource)
    except _COLLECTION_ERRORS:
        return _pressure_placeholder(resource, STATUS_UNAVAILABLE)


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
    """Collect fixed, non-identifying metrics. Dependencies can be injected for tests.

    Keys present in schema 0.1 keep their order and meaning; keys added in 0.2
    (swap, pressure) are appended after them.
    """
    # As in v0.1, the timestamp marks the start of collection: the clock is
    # read before any metric source.
    timestamp = _timestamp(clock)
    loadavg = _safe_text("/proc/loadavg", read_text)
    meminfo = _safe_text("/proc/meminfo", read_text)  # read once, parsed twice
    uptime = _safe_text("/proc/uptime", read_text)
    return {
        "schema_version": SCHEMA_VERSION,
        "timestamp_utc": timestamp,
        "load_average": _safe_parse(loadavg, parse_loadavg, METRIC_FIELDS["load_average"]),
        "memory": _safe_parse(meminfo, parse_meminfo, METRIC_FIELDS["memory"]),
        "disk_root": _safe_disk(statvfs),
        "uptime": _safe_parse(uptime, parse_uptime, METRIC_FIELDS["uptime"]),
        "swap": _safe_parse(meminfo, parse_swap, METRIC_FIELDS["swap"]),
        "pressure": {
            resource: _safe_pressure(resource, read_text) for resource in PRESSURE_LINES
        },
    }


def has_unavailable(snapshot: dict) -> bool:
    """True if any applicable reading failed.

    Intended for snapshots produced by collect_snapshot(). PSI blocks marked
    "unsupported" are not failures: the interface is simply not exposed, so
    they do not change the exit code. A PSI block claiming "ok" without a
    window object for each reported line is treated as a failure.
    """
    # The timestamp is missing if it is None or an empty string.
    if not snapshot.get("timestamp_utc"):
        return True
    if any(snapshot.get(metric, {}).get("status") != STATUS_OK for metric in METRIC_FIELDS):
        return True
    pressure = snapshot.get("pressure")
    if not isinstance(pressure, dict):
        return True
    for resource, kinds in PRESSURE_LINES.items():
        block = pressure.get(resource)
        if not isinstance(block, dict):
            return True
        status = block.get("status")
        if status == STATUS_UNSUPPORTED:
            continue
        if status != STATUS_OK or not all(isinstance(block.get(kind), dict) for kind in kinds):
            return True
    return False
