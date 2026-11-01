"""Contract tests for report privacy with exclusively synthetic inputs."""

from datetime import datetime
import json
import math
import re
import unittest

from linux_health_reporter.renderers import render_json, render_markdown
from tests.test_collectors import synthetic_snapshot


# Exact output allowlist: unknown keys and nested objects must fail the tests.
# This is a test contract, not runtime validation of untrusted external input.
WINDOW = object()  # PSI window: null or {avg10, avg60, avg300}; checked separately.
PUBLIC_SCHEMA = {
    "schema_version": None,
    "timestamp_utc": None,
    "load_average": {"status": None, "1m": None, "5m": None, "15m": None},
    "memory": {"status": None, "total_bytes": None, "available_bytes": None},
    "disk_root": {"status": None, "total_bytes": None, "available_bytes": None},
    "uptime": {"status": None, "uptime_seconds": None},
    "swap": {"status": None, "total_bytes": None, "free_bytes": None},
    "pressure": {
        "cpu": {"status": None, "some": WINDOW},
        "memory": {"status": None, "some": WINDOW, "full": WINDOW},
        "io": {"status": None, "some": WINDOW, "full": WINDOW},
    },
}
SCALAR_METRICS = ("load_average", "memory", "disk_root", "uptime", "swap")
PRESSURE_WINDOWS = ("avg10", "avg60", "avg300")


class PrivacyTests(unittest.TestCase):
    def assert_public_schema(self, snapshot):
        def check(value, expected, location):
            if expected is WINDOW:
                return
            if isinstance(expected, dict):
                self.assertIsInstance(value, dict, location)
                self.assertEqual(set(value), set(expected), location)
                for key, child in expected.items():
                    check(value[key], child, location + "." + key)
            else:
                self.assertNotIsInstance(value, (dict, list, tuple, set), location)

        check(snapshot, PUBLIC_SCHEMA, "snapshot")
        self.assertEqual(snapshot["schema_version"], "0.2")
        ts = snapshot["timestamp_utc"]
        if ts is not None:
            self.assertIsInstance(ts, str)
            self.assertIsNotNone(
                re.fullmatch(
                    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z",
                    ts,
                ),
                "timestamp_utc must use strict UTC YYYY-MM-DDTHH:MM:SSZ",
            )
            try:
                datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ")
            except ValueError as exc:
                self.fail(f"timestamp_utc contains an invalid calendar date: {exc}")

        for name in SCALAR_METRICS:
            metric = snapshot[name]
            # "unsupported" is reserved for PSI blocks and never valid here.
            self.assertIn(metric["status"], ("ok", "unavailable"))
            for key, value in metric.items():
                if key == "status":
                    continue
                location = name + "." + key
                if metric["status"] == "unavailable":
                    self.assertIsNone(value, location)
                elif name in ("uptime", "memory", "disk_root", "swap"):
                    self.assertIs(type(value), int, location)
                    self.assertGreaterEqual(value, 0, location)
                else:
                    self.assertIn(type(value), (int, float), location)
                    self.assertTrue(math.isfinite(value), location)
                    self.assertGreaterEqual(value, 0, location)

            if metric["status"] == "ok" and name in ("memory", "disk_root"):
                self.assertGreater(metric["total_bytes"], 0, name)
                self.assertLessEqual(
                    metric["available_bytes"], metric["total_bytes"], name
                )
            if metric["status"] == "ok" and name == "swap":
                self.assertLessEqual(metric["free_bytes"], metric["total_bytes"], name)

        for resource, block in snapshot["pressure"].items():
            self.assertIn(block["status"], ("ok", "unavailable", "unsupported"), resource)
            for kind in (key for key in block if key != "status"):
                location = f"pressure.{resource}.{kind}"
                window = block[kind]
                if block["status"] != "ok":
                    self.assertIsNone(window, location)
                    continue
                self.assertIsInstance(window, dict, location)
                self.assertEqual(set(window), set(PRESSURE_WINDOWS), location)
                for average in PRESSURE_WINDOWS:
                    value = window[average]
                    self.assertIs(type(value), float, location + "." + average)
                    self.assertTrue(math.isfinite(value), location)
                    self.assertGreaterEqual(value, 0, location)
                    self.assertLessEqual(value, 100, location)

    def test_schema_does_not_include_identifying_fields(self):
        self.assert_public_schema(synthetic_snapshot())

    def test_schema_rejects_unapproved_top_level_metadata(self):
        snapshot = synthetic_snapshot()
        snapshot["metadata"] = {"hostname": "test-host.example.invalid"}
        with self.assertRaises(AssertionError):
            self.assert_public_schema(snapshot)

    def test_schema_rejects_unapproved_nested_metadata(self):
        snapshot = synthetic_snapshot()
        snapshot["memory"]["hostname"] = "test-host.example.invalid"
        with self.assertRaises(AssertionError):
            self.assert_public_schema(snapshot)

    def test_schema_rejects_nested_object_in_numeric_field(self):
        snapshot = synthetic_snapshot()
        snapshot["memory"]["total_bytes"] = {"hostname": "test-host.example.invalid"}
        with self.assertRaises(AssertionError):
            self.assert_public_schema(snapshot)

    def test_schema_rejects_identifier_string_in_numeric_field(self):
        snapshot = synthetic_snapshot()
        snapshot["uptime"]["uptime_seconds"] = "test-host.example.invalid"
        with self.assertRaises(AssertionError):
            self.assert_public_schema(snapshot)

    def test_schema_rejects_invalid_timestamp_formats(self):
        invalid = (
            "",
            "test-host.example.invalid",
            "2026-01-02T04:04:05+01:00",
            "2026-02-30T01:02:03Z",
            "2026-01-02T03:04:05.000000Z",
            "2026-1-02T03:04:05Z",
        )
        for value in invalid:
            with self.subTest(value=value):
                snapshot = synthetic_snapshot()
                snapshot["timestamp_utc"] = value
                with self.assertRaises(AssertionError):
                    self.assert_public_schema(snapshot)

    def test_schema_accepts_unavailable_timestamp(self):
        snapshot = synthetic_snapshot()
        snapshot["timestamp_utc"] = None
        self.assert_public_schema(snapshot)

    def test_schema_rejects_invalid_numeric_measurements(self):
        cases = (
            ("memory", "total_bytes", -1),
            ("memory", "total_bytes", 0),
            ("memory", "total_bytes", 1.5),
            ("memory", "available_bytes", 10 ** 20),
            ("memory", "available_bytes", -1),
            ("disk_root", "total_bytes", 0),
            ("disk_root", "available_bytes", 10 ** 20),
            ("load_average", "1m", float("nan")),
            ("load_average", "15m", float("inf")),
            ("load_average", "5m", -0.01),
            ("uptime", "uptime_seconds", -5),
            ("uptime", "uptime_seconds", 1.5),
            ("uptime", "uptime_seconds", True),
        )
        for metric, field, value in cases:
            with self.subTest(metric=metric, field=field, value=repr(value)):
                snapshot = synthetic_snapshot()
                snapshot[metric][field] = value
                with self.assertRaises(AssertionError):
                    self.assert_public_schema(snapshot)

    def test_schema_accepts_available_equal_total(self):
        snapshot = synthetic_snapshot()
        for name in ("memory", "disk_root"):
            snapshot[name]["available_bytes"] = snapshot[name]["total_bytes"]
        self.assert_public_schema(snapshot)

    def test_schema_accepts_unsupported_and_unavailable_pressure(self):
        snapshot = synthetic_snapshot()
        snapshot["pressure"]["cpu"] = {"status": "unsupported", "some": None}
        snapshot["pressure"]["io"] = {"status": "unavailable", "some": None, "full": None}
        self.assert_public_schema(snapshot)

    def test_schema_accepts_system_without_swap(self):
        snapshot = synthetic_snapshot()
        snapshot["swap"] = {"status": "ok", "total_bytes": 0, "free_bytes": 0}
        self.assert_public_schema(snapshot)

    def test_schema_rejects_invalid_swap_and_pressure(self):
        def set_path(snapshot, path, value):
            target = snapshot
            for key in path[:-1]:
                target = target[key]
            target[path[-1]] = value

        cases = (
            (("swap", "free_bytes"), 10 ** 20),          # free > total
            (("swap", "total_bytes"), -1),
            (("swap", "free_bytes"), 1.5),
            (("swap", "status"), "unsupported"),         # reserved for PSI
            (("memory", "status"), "unsupported"),
            (("pressure", "cpu", "full"), None),          # CPU full is never reported
            (("pressure", "cpu", "status"), "error"),
            (("pressure", "memory", "reason"), "permission denied"),
            (("pressure", "io", "some", "avg10"), 100.5),
            (("pressure", "io", "some", "avg60"), -0.1),
            (("pressure", "io", "full", "avg300"), float("nan")),
            (("pressure", "memory", "some", "avg10"), "test-host.example.invalid"),
            (("pressure", "memory", "some", "avg10"), 1),  # must be float
            (("pressure", "memory", "full", "total"), 12345),
            (("pressure", "hostname"), "test-host.example.invalid"),
        )
        for path, value in cases:
            with self.subTest(path=path, value=repr(value)):
                snapshot = synthetic_snapshot()
                set_path(snapshot, path, value)
                with self.assertRaises(AssertionError):
                    self.assert_public_schema(snapshot)

    def test_schema_rejects_values_in_non_ok_pressure_block(self):
        snapshot = synthetic_snapshot()
        snapshot["pressure"]["memory"]["status"] = "unsupported"
        with self.assertRaises(AssertionError):
            self.assert_public_schema(snapshot)

    def test_report_contains_only_synthetic_measurements(self):
        report = render_json(synthetic_snapshot())
        parsed = json.loads(report)
        self.assert_public_schema(parsed)
        self.assertEqual(parsed["memory"]["total_bytes"], 16777216000)
        markdown = render_markdown(parsed)
        # Deliberately fictitious identifiers; never put private host data in tests.
        for private_marker in (
            "test-host.example.invalid",
            "/home/synthetic-user",
            "192.0.2.44",
            "198.51.100.42",
        ):
            self.assertNotIn(private_marker, report)
            self.assertNotIn(private_marker, markdown)


if __name__ == "__main__":
    unittest.main()
