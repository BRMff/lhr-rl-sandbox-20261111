"""Synthetic-only collector tests: never touch the real /proc or filesystem."""

from datetime import datetime, timezone
from types import SimpleNamespace
import unittest

from linux_health_reporter.collectors import (
    PROC_SOURCES,
    collect_snapshot,
    has_unavailable,
    parse_disk_statvfs,
    parse_loadavg,
    parse_meminfo,
    parse_uptime,
)


SYNTHETIC = {
    "/proc/loadavg": "0.42 0.36 0.31 1/160 99\n",
    "/proc/meminfo": (
        "MemTotal: 16384000 kB\nMemFree: 256000 kB\nMemAvailable: 9216000 kB\n"
        "SwapCached: 0 kB\nSwapTotal: 2097152 kB\nSwapFree: 1992294 kB\n"
    ),
    "/proc/uptime": "86400.84 303.10\n",
    "/proc/pressure/cpu": (
        "some avg10=1.25 avg60=0.80 avg300=0.40 total=123456\n"
        "full avg10=0.00 avg60=0.00 avg300=0.00 total=0\n"
    ),
    "/proc/pressure/memory": (
        "some avg10=0.50 avg60=0.25 avg300=0.10 total=2000\n"
        "full avg10=0.20 avg60=0.10 avg300=0.05 total=1000\n"
    ),
    "/proc/pressure/io": (
        "some avg10=3.00 avg60=2.50 avg300=1.75 total=3000\n"
        "full avg10=1.50 avg60=1.25 avg300=0.75 total=1500\n"
    ),
}
SYNTHETIC_DISK = SimpleNamespace(f_frsize=4096, f_blocks=125000000, f_bavail=62500000)


def synthetic_reader(path: str) -> str:
    return SYNTHETIC[path]


def synthetic_statvfs(path: str):
    if path != "/":
        raise AssertionError("unexpected filesystem target")
    return SYNTHETIC_DISK


def synthetic_clock():
    return datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)


def synthetic_snapshot():
    return collect_snapshot(
        read_text=synthetic_reader,
        statvfs=synthetic_statvfs,
        clock=synthetic_clock,
    )


class ParserTests(unittest.TestCase):
    def test_load_average(self):
        self.assertEqual(
            parse_loadavg(SYNTHETIC["/proc/loadavg"]),
            {"status": "ok", "1m": 0.42, "5m": 0.36, "15m": 0.31},
        )

    def test_load_rejects_malformed_and_nonfinite(self):
        for value in ("0.1 0.2", "nan 0.2 0.3", "-1 0.2 0.3", "inf 0.2 0.3"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                parse_loadavg(value)

    def test_memory_uses_available_not_free(self):
        self.assertEqual(
            parse_meminfo(SYNTHETIC["/proc/meminfo"]),
            {"status": "ok", "total_bytes": 16777216000, "available_bytes": 9437184000},
        )

    def test_memory_rejects_inconsistent_input(self):
        samples = (
            "MemTotal: 10 kB\n",
            "MemTotal: 10 MB\nMemAvailable: 2 kB\n",
            "MemTotal: 10 kB\nMemAvailable: 12 kB\n",
            "MemTotal: 10 kB\nMemTotal: 10 kB\nMemAvailable: 2 kB\n",
            "MemTotal: 0 kB\nMemAvailable: 0 kB\n",
        )
        for text in samples:
            with self.subTest(text=text), self.assertRaises(ValueError):
                parse_meminfo(text)

    def test_disk_uses_unprivileged_available_blocks(self):
        self.assertEqual(
            parse_disk_statvfs(SYNTHETIC_DISK),
            {"status": "ok", "total_bytes": 512000000000, "available_bytes": 256000000000},
        )

    def test_disk_rejects_invalid_data(self):
        for item in (
            SimpleNamespace(f_frsize=0, f_blocks=10, f_bavail=2),
            SimpleNamespace(f_frsize=4096, f_blocks=10, f_bavail=-1),
            SimpleNamespace(f_frsize=4096, f_blocks=10, f_bavail=12),
        ):
            with self.assertRaises(ValueError):
                parse_disk_statvfs(item)

    def test_disk_boundary_conditions(self):
        with self.assertRaises(ValueError):
            parse_disk_statvfs(
                SimpleNamespace(f_frsize=4096, f_blocks=0, f_bavail=0)
            )
        self.assertEqual(
            parse_disk_statvfs(
                SimpleNamespace(f_frsize=4096, f_blocks=100, f_bavail=100)
            ),
            {"status": "ok", "total_bytes": 409600, "available_bytes": 409600},
        )

    def test_load_rejects_overflowing_float(self):
        with self.assertRaises(ValueError):
            parse_loadavg("1e400 0 0")

    def test_uptime_truncates_fractional_seconds(self):
        self.assertEqual(parse_uptime("86400.84 303.10"), {"status": "ok", "uptime_seconds": 86400})

    def test_uptime_rejects_negative_and_nonfinite(self):
        for sample in ("", "-1 2", "inf 1", "nan 1"):
            with self.subTest(value=sample), self.assertRaises(ValueError):
                parse_uptime(sample)


class CollectionTests(unittest.TestCase):
    def test_complete_snapshot_is_fully_synthetic(self):
        actual_reads = []
        actual_stat_calls = []

        def reader(path):
            actual_reads.append(path)
            return SYNTHETIC[path]

        def statvfs(path):
            actual_stat_calls.append(path)
            return SYNTHETIC_DISK

        result = collect_snapshot(read_text=reader, statvfs=statvfs, clock=synthetic_clock)
        # v0.2: each allowlisted source is read exactly once (meminfo included).
        self.assertEqual(actual_reads, list(PROC_SOURCES))
        self.assertEqual(actual_stat_calls, ["/"])
        self.assertEqual(result["schema_version"], "0.2")
        self.assertEqual(result["timestamp_utc"], "2026-01-02T03:04:05Z")
        self.assertFalse(has_unavailable(result))

    def test_metric_read_errors_are_private_unavailable(self):
        def reader(path):
            if path == "/proc/meminfo":
                raise PermissionError("private_password_123 and internal hostname")
            return SYNTHETIC[path]

        def statvfs(path):
            raise OSError("internal filesystem failure: secret=1234")

        result = collect_snapshot(
            read_text=reader, statvfs=statvfs, clock=synthetic_clock
        )
        self.assertEqual(
            result["memory"],
            {"status": "unavailable", "total_bytes": None, "available_bytes": None},
        )
        self.assertEqual(result["disk_root"]["status"], "unavailable")
        self.assertIsNone(result["disk_root"]["total_bytes"])
        self.assertTrue(has_unavailable(result))
        self.assertNotIn("private_password_123", repr(result))
        self.assertNotIn("internal hostname", repr(result))
        self.assertNotIn("secret=1234", repr(result))

    def test_corrupted_source_is_unavailable_not_zero(self):
        source = dict(SYNTHETIC, **{"/proc/loadavg": "nan inf 0.0"})
        result = collect_snapshot(
            read_text=lambda path: source[path],
            statvfs=synthetic_statvfs,
            clock=synthetic_clock,
        )
        self.assertEqual(result["load_average"]["status"], "unavailable")
        self.assertIsNone(result["load_average"]["1m"])

    def test_naive_clock_is_not_mislabelled_as_utc(self):
        result = collect_snapshot(
            read_text=synthetic_reader,
            statvfs=synthetic_statvfs,
            clock=lambda: datetime(2026, 1, 2),
        )
        self.assertIsNone(result["timestamp_utc"])
        self.assertTrue(has_unavailable(result))

    def test_timezone_conversion_removes_microseconds(self):
        from datetime import timedelta

        result = collect_snapshot(
            read_text=synthetic_reader,
            statvfs=synthetic_statvfs,
            clock=lambda: datetime(
                2026, 1, 2, 4, 4, 5, 987654,
                tzinfo=timezone(timedelta(hours=1)),
            ),
        )
        self.assertEqual(result["timestamp_utc"], "2026-01-02T03:04:05Z")
        self.assertFalse(has_unavailable(result))

    def test_empty_timestamp_counts_as_unavailable(self):
        result = synthetic_snapshot()
        result["timestamp_utc"] = ""
        self.assertTrue(has_unavailable(result))

    def test_clock_oserror_is_unavailable_and_cli_returns_one(self):
        import contextlib
        from io import StringIO
        import json
        from unittest.mock import patch

        from linux_health_reporter.__main__ import main

        def clock_failure():
            raise OSError("simulated inaccessible clock: synthetic-private-context")

        result = collect_snapshot(
            read_text=synthetic_reader,
            statvfs=synthetic_statvfs,
            clock=clock_failure,
        )
        self.assertIsNone(result["timestamp_utc"])
        self.assertTrue(has_unavailable(result))
        self.assertTrue(
            all(result[name]["status"] == "ok" for name in (
                "load_average", "memory", "disk_root", "uptime"
            ))
        )

        output = StringIO()
        with patch("linux_health_reporter.__main__.collect_snapshot", return_value=result):
            with contextlib.redirect_stdout(output):
                exit_code = main(["--format", "json"])
        published = output.getvalue()
        self.assertEqual(exit_code, 1)
        self.assertIsNone(json.loads(published)["timestamp_utc"])
        self.assertNotIn("synthetic-private-context", published)


if __name__ == "__main__":
    unittest.main()
