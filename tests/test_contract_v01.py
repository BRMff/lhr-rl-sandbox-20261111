"""Backward-compatibility contract: schema 0.2 must be additive over 0.1.

tests/fixtures/v0.1-sample.json is the unmodified examples/sample.json from the
v0.1.0 release. It must not be edited.
"""

import hashlib
import json
from pathlib import Path
import unittest

from linux_health_reporter.collectors import collect_snapshot
from linux_health_reporter.renderers import render_json
from tests.test_collectors import SYNTHETIC, synthetic_clock, synthetic_snapshot

V01_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "v0.1-sample.json"
# SHA-256 of examples/sample.json at tag v0.1.0 (git blob b4fa4c88).
V01_FIXTURE_SHA256 = "1558a77c3a87f34706531126a283172d88cc7b4c6a897183292f216c1e117ebb"
V01_KEYS = ("schema_version", "timestamp_utc", "load_average", "memory", "disk_root", "uptime")


class SchemaV01CompatibilityTests(unittest.TestCase):
    def setUp(self):
        self.v01 = json.loads(V01_FIXTURE.read_text(encoding="utf-8"))
        self.v02 = json.loads(render_json(synthetic_snapshot()))

    def test_fixture_is_the_v01_release_sample(self):
        # Review R-03: pin the fixture's provenance, not only its content.
        digest = hashlib.sha256(V01_FIXTURE.read_bytes()).hexdigest()
        self.assertEqual(digest, V01_FIXTURE_SHA256)
        self.assertEqual(self.v01["schema_version"], "0.1")
        self.assertEqual(tuple(self.v01), V01_KEYS)

    def test_v01_unavailable_shapes_are_preserved(self):
        # Every v0.1 metric keeps its exact field set, all null, when collection fails.
        def failing_reader(path):
            raise PermissionError("synthetic")

        def failing_statvfs(path):
            raise OSError("synthetic")

        snapshot = json.loads(
            render_json(
                collect_snapshot(read_text=failing_reader, statvfs=failing_statvfs, clock=synthetic_clock)
            )
        )
        self.assertEqual(tuple(snapshot)[: len(V01_KEYS)], V01_KEYS)
        for key in V01_KEYS[2:]:
            with self.subTest(key=key):
                expected = {"status": "unavailable", **{f: None for f in self.v01[key] if f != "status"}}
                self.assertEqual(snapshot[key], expected)

    def test_v01_values_for_alternative_inputs(self):
        # A second, independent input set: v0.1 fields must keep v0.1 semantics.
        source = dict(
            SYNTHETIC,
            **{
                "/proc/loadavg": "2.50 1.00 0.00 3/300 1234\n",
                "/proc/meminfo": "MemTotal: 2048 kB\nMemAvailable: 2048 kB\nSwapTotal: 0 kB\nSwapFree: 0 kB\n",
                "/proc/uptime": "59.99 1.00\n",
            },
        )
        from types import SimpleNamespace

        snapshot = collect_snapshot(
            read_text=lambda path: source[path],
            statvfs=lambda path: SimpleNamespace(f_frsize=512, f_blocks=8, f_bavail=0),
            clock=synthetic_clock,
        )
        self.assertEqual(snapshot["load_average"], {"status": "ok", "1m": 2.5, "5m": 1.0, "15m": 0.0})
        self.assertEqual(snapshot["memory"], {"status": "ok", "total_bytes": 2097152, "available_bytes": 2097152})
        self.assertEqual(snapshot["disk_root"], {"status": "ok", "total_bytes": 4096, "available_bytes": 0})
        self.assertEqual(snapshot["uptime"], {"status": "ok", "uptime_seconds": 59})

    def test_v01_keys_keep_order_and_come_first(self):
        self.assertEqual(tuple(self.v02)[: len(V01_KEYS)], V01_KEYS)
        self.assertEqual(tuple(self.v02)[len(V01_KEYS):], ("swap", "pressure"))

    def test_v01_metrics_are_unchanged_for_the_same_inputs(self):
        for key in V01_KEYS:
            if key == "schema_version":
                continue
            with self.subTest(key=key):
                self.assertEqual(self.v02[key], self.v01[key])

    def test_v01_field_names_and_types_are_preserved(self):
        for key in V01_KEYS[2:]:
            with self.subTest(key=key):
                self.assertEqual(tuple(self.v02[key]), tuple(self.v01[key]))
                for field, value in self.v01[key].items():
                    self.assertIs(type(self.v02[key][field]), type(value), f"{key}.{field}")

    def test_only_schema_version_differs_among_v01_keys(self):
        changed = [key for key in V01_KEYS if self.v01[key] != self.v02[key]]
        self.assertEqual(changed, ["schema_version"])
        self.assertEqual(self.v02["schema_version"], "0.2")


if __name__ == "__main__":
    unittest.main()
