"""Pure, deterministic formatting helpers for human-readable output.

These functions only format numbers already present in a snapshot. They do
not read the system and are safe to reuse in any presentation layer.
"""

from __future__ import annotations

import math

_IEC_UNITS = ("KiB", "MiB", "GiB", "TiB", "PiB", "EiB")


def _require_non_negative_int(value: object, name: str) -> int:
    if type(value) is not int or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")
    return value


def format_bytes(value: object) -> str:
    """Format a byte count with IEC binary units and one decimal place.

    Values below 1 KiB are shown as whole bytes. A value that rounds up to
    1024 of a unit is promoted to the next unit (1048575 B -> "1.0 MiB").
    """
    size = _require_non_negative_int(value, "byte count")
    if size < 1024:
        return f"{size} B"
    scaled = float(size)
    for index, unit in enumerate(_IEC_UNITS):
        scaled /= 1024
        is_last = index == len(_IEC_UNITS) - 1
        if round(scaled, 1) < 1024 or is_last:
            return f"{scaled:.1f} {unit}"
    raise AssertionError("unreachable")  # pragma: no cover


def format_duration(value: object) -> str:
    """Format whole seconds as days, hours and minutes (truncated, never rounded up)."""
    seconds = _require_non_negative_int(value, "duration")
    if seconds < 60:
        return f"{seconds} s"
    minutes, _ = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    days, hours = divmod(hours, 24)
    if days:
        return f"{days} d {hours:02d} h {minutes:02d} min"
    if hours:
        return f"{hours} h {minutes:02d} min"
    return f"{minutes} min"


def format_percent(part: object, total: object) -> str:
    """Format part/total as a percentage with one decimal place."""
    numerator = _require_non_negative_int(part, "part")
    denominator = _require_non_negative_int(total, "total")
    if denominator == 0 or numerator > denominator:
        raise ValueError("invalid percentage operands")
    return f"{numerator * 100 / denominator:.1f} %"


def format_ratio_triplet(values: tuple[object, ...], suffix: str = "") -> str:
    """Format three finite non-negative numbers as 'a / b / c' with two decimals."""
    if len(values) != 3:
        raise ValueError("expected three values")
    parts = []
    for value in values:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError("expected a number")
        if not math.isfinite(value) or value < 0:
            raise ValueError("expected a finite non-negative number")
        parts.append(f"{value:.2f}")
    return " / ".join(parts) + suffix
