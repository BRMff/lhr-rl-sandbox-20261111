"""Backward-compatibility contract: schema 0.2 must be additive over 0.1.

tests/fixtures/v0.1-sample.json is the unmodified examples/sample.json from the
v0.1.0 release. It must not be edited.
"""

import json
from pathlib import Path
import unittest

from linux_health_reporter.renderers import render_json
from tests.test_collectors import synthetic_snapshot

V01_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "v0.1-sample.json"
V01_KEYS = ("schema_version", "timestamp_utc", "load_average", "memory", "disk_root", "uptime")


class SchemaV01CompatibilityTests(unittest.TestCase):
    def setUp(self):
        self.v01 = json.loads(V01_FIXTURE.read_text(encoding="utf-8"))
        self.v02 = json.loads(render_json(synthetic_snapshot()))

    def test_fixture_is_the_v01_release_sample(self):
        self.assertEqual(self.v01["schema_version"], "0.1")
        self.assertEqual(tuple(self.v01), V01_KEYS)

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
