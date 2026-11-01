"""Tests for the CI wheel inspector (ci/check_wheel.py). No build is performed."""

import importlib.util
from pathlib import Path
import unittest

_SPEC = importlib.util.spec_from_file_location(
    "check_wheel", Path(__file__).resolve().parents[1] / "ci" / "check_wheel.py"
)
check_wheel = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(check_wheel)

DIST = "linux_health_reporter-0.2.0.dist-info/"
GOOD_NAMES = [
    "linux_health_reporter/__init__.py",
    "linux_health_reporter/__main__.py",
    "linux_health_reporter/collectors.py",
    "linux_health_reporter/renderers.py",
    "linux_health_reporter/units.py",
    DIST + "licenses/LICENSE",
    DIST + "METADATA",
    DIST + "WHEEL",
    DIST + "entry_points.txt",
    DIST + "top_level.txt",
    DIST + "RECORD",
]
GOOD_METADATA = (
    "Metadata-Version: 2.4\nName: linux-health-reporter\nVersion: 0.2.0\n"
    "License-Expression: MIT\n"
)


class CheckWheelTests(unittest.TestCase):
    def test_expected_wheel_passes(self):
        self.assertEqual(check_wheel.find_problems(GOOD_NAMES, GOOD_METADATA), ([], "0.2.0"))

    def test_rejects_unexpected_members(self):
        # Review R-05: stray files, including in another .dist-info, are rejected.
        cases = {
            "other dist-info": "other.dist-info/payload.txt",
            "extra file in dist-info": DIST + "payload.txt",
            "tests packaged": "tests/test_collectors.py",
            "top-level module": "evil.py",
            "nested package file": "linux_health_reporter/data/telemetry.json",
            "non-python package file": "linux_health_reporter/notes.txt",
        }
        for name, extra in cases.items():
            with self.subTest(case=name):
                problems, _ = check_wheel.find_problems(GOOD_NAMES + [extra], GOOD_METADATA)
                self.assertTrue(problems)

    def test_rejects_dist_info_for_another_version(self):
        names = [n.replace("0.2.0", "0.1.0") for n in GOOD_NAMES]
        problems, _ = check_wheel.find_problems(names, GOOD_METADATA)
        self.assertTrue(problems)

    def test_rejects_bad_metadata(self):
        cases = {
            "runtime dependency": GOOD_METADATA + "Requires-Dist: requests\n",
            "wrong license": GOOD_METADATA.replace("MIT", "GPL-3.0-only"),
            "missing version": GOOD_METADATA.replace("Version: 0.2.0\n", ""),
        }
        for name, metadata in cases.items():
            with self.subTest(case=name):
                problems, _ = check_wheel.find_problems(GOOD_NAMES, metadata)
                self.assertTrue(problems)

    def test_rejects_missing_package(self):
        names = [n for n in GOOD_NAMES if not n.endswith("collectors.py")]
        problems, _ = check_wheel.find_problems(names, GOOD_METADATA)
        self.assertTrue(problems)


if __name__ == "__main__":
    unittest.main()
