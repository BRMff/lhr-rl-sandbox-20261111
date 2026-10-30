"""Deterministic JSON and Markdown output for collected metrics."""

from __future__ import annotations

import json


def render_json(snapshot: dict) -> str:
    return json.dumps(snapshot, indent=2, ensure_ascii=False, allow_nan=False)


def _metric(snapshot: dict, name: str, fields: tuple[str, ...]) -> str:
    metric = snapshot[name]
    if metric["status"] != "ok":
        return "Unavailable"
    return " / ".join(str(metric[field]) for field in fields)


def render_markdown(snapshot: dict) -> str:
    timestamp = snapshot.get("timestamp_utc") or "Unavailable"
    entries = [
        ("Load average (1m / 5m / 15m)", _metric(snapshot, "load_average", ("1m", "5m", "15m"))),
        ("RAM total / available (bytes)", _metric(snapshot, "memory", ("total_bytes", "available_bytes"))),
        ("Root filesystem total / available (bytes)", _metric(snapshot, "disk_root", ("total_bytes", "available_bytes"))),
        ("Uptime (seconds)", _metric(snapshot, "uptime", ("uptime_seconds",))),
    ]
    result = [
        "# Linux Health Report",
        "",
        f"Generated (UTC): {timestamp}",
        "",
        "| Metric | Value |",
        "| --- | --- |",
    ]
    result.extend(f"| {label} | {value} |" for label, value in entries)
    result.append("")
    return "\n".join(result)
