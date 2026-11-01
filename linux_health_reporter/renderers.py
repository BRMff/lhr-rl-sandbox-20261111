"""Deterministic JSON and Markdown output for collected metrics.

JSON is the structured, versioned interface. Markdown is a presentation
format for people: its layout and units may change between versions.
"""

from __future__ import annotations

import json

from .collectors import PRESSURE_LINES
from .units import format_bytes, format_duration, format_percent, format_ratio_triplet

UNAVAILABLE = "Unavailable"
UNSUPPORTED = "Not supported by kernel"
NOT_APPLICABLE = "n/a"

_PRESSURE_ROWS = (("cpu", "CPU"), ("memory", "Memory"), ("io", "I/O"))


def render_json(snapshot: dict) -> str:
    return json.dumps(snapshot, indent=2, ensure_ascii=False, allow_nan=False)


def _is_ok(metric: object) -> bool:
    return isinstance(metric, dict) and metric.get("status") == "ok"


def _capacity(metric: object, part_field: str) -> str:
    if not _is_ok(metric):
        return UNAVAILABLE
    part, total = metric[part_field], metric["total_bytes"]
    return f"{format_bytes(part)} of {format_bytes(total)} ({format_percent(part, total)})"


def _load(metric: object) -> str:
    if not _is_ok(metric):
        return UNAVAILABLE
    return format_ratio_triplet((metric["1m"], metric["5m"], metric["15m"]))


def _swap(metric: object) -> str:
    if _is_ok(metric) and metric["total_bytes"] == 0:
        return "No swap configured"
    return _capacity(metric, "free_bytes")


def _uptime(metric: object) -> str:
    if not _is_ok(metric):
        return UNAVAILABLE
    return format_duration(metric["uptime_seconds"])


def _pressure_cell(block: object, resource: str, kind: str) -> str:
    if kind not in PRESSURE_LINES[resource]:
        return NOT_APPLICABLE
    if not isinstance(block, dict):
        return UNAVAILABLE
    status = block.get("status")
    if status == "unsupported":
        return UNSUPPORTED
    if status != "ok":
        return UNAVAILABLE
    window = block[kind]
    return format_ratio_triplet((window["avg10"], window["avg60"], window["avg300"]), " %")


def render_markdown(snapshot: dict) -> str:
    timestamp = snapshot.get("timestamp_utc") or UNAVAILABLE
    entries = [
        ("Load average (1m / 5m / 15m)", _load(snapshot.get("load_average"))),
        ("Memory available", _capacity(snapshot.get("memory"), "available_bytes")),
        ("Swap free", _swap(snapshot.get("swap"))),
        ("Root filesystem available", _capacity(snapshot.get("disk_root"), "available_bytes")),
        ("Uptime", _uptime(snapshot.get("uptime"))),
    ]
    pressure = snapshot.get("pressure")
    pressure = pressure if isinstance(pressure, dict) else {}
    result = [
        "# Linux Health Report",
        "",
        f"Generated (UTC): {timestamp}",
        "",
        "| Metric | Value |",
        "| --- | --- |",
    ]
    result.extend(f"| {label} | {value} |" for label, value in entries)
    result.extend(
        [
            "",
            "## Pressure stall information",
            "",
            "Share of time tasks were stalled, averaged over 10 s / 60 s / 300 s.",
            "",
            "| Resource | Some | Full |",
            "| --- | --- | --- |",
        ]
    )
    for key, label in _PRESSURE_ROWS:
        block = pressure.get(key)
        result.append(
            f"| {label} | {_pressure_cell(block, key, 'some')} "
            f"| {_pressure_cell(block, key, 'full')} |"
        )
    result.append("")
    return "\n".join(result)
