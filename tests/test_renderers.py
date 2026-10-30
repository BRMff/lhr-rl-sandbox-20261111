"""Renderers and CLI tests use injected fixtures only."""

import contextlib
from io import StringIO
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from linux_health_reporter.__main__ import main
from linux_health_reporter.renderers import render_json, render_markdown
from tests.test_collectors import synthetic_snapshot


class RendererTests(unittest.TestCase):
    def test_json_is_parseable_and_preserves_values(self):
        snapshot = synthetic_snapshot()
        text = render_json(snapshot)
        self.assertEqual(json.loads(text), snapshot)
        self.assertIn('"schema_version": "0.1"', text)

    def test_sample_json_matches_synthetic_fixture(self):
        sample = Path(__file__).resolve().parents[1] / "examples" / "sample.json"
        expected = render_json(synthetic_snapshot())
        self.assertEqual(sample.read_text(encoding="utf-8").rstrip("\n"), expected)
        self.assertEqual(json.loads(sample.read_text(encoding="utf-8")), synthetic_snapshot())

    def test_markdown_has_expected_sections(self):
        text = render_markdown(synthetic_snapshot())
        self.assertIn("# Linux Health Report", text)
        self.assertIn("2026-01-02T03:04:05Z", text)
        self.assertIn("Load average (1m / 5m / 15m)", text)
        self.assertIn("512000000000 / 256000000000", text)

    def test_unavailable_renders_without_raw_exception(self):
        snapshot = synthetic_snapshot()
        snapshot["memory"] = {
            "status": "unavailable",
            "total_bytes": None,
            "available_bytes": None,
        }
        rendered = render_markdown(snapshot)
        self.assertIn("Unavailable", rendered)
        self.assertNotIn("None / None", rendered)


class CLITests(unittest.TestCase):
    def test_json_stdout_success(self):
        with patch("linux_health_reporter.__main__.collect_snapshot", return_value=synthetic_snapshot()):
            output = StringIO()
            with contextlib.redirect_stdout(output):
                code = main(["--format", "json"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output.getvalue())["memory"]["status"], "ok")

    def test_markdown_stdout_success(self):
        with patch("linux_health_reporter.__main__.collect_snapshot", return_value=synthetic_snapshot()):
            output = StringIO()
            with contextlib.redirect_stdout(output):
                code = main(["--format", "markdown"])
        self.assertEqual(code, 0)
        self.assertTrue(output.getvalue().startswith("# Linux Health Report"))

    def test_partial_collection_exit_code_is_one(self):
        snapshot = synthetic_snapshot()
        snapshot["uptime"] = {"status": "unavailable", "uptime_seconds": None}
        with patch("linux_health_reporter.__main__.collect_snapshot", return_value=snapshot):
            output = StringIO()
            with contextlib.redirect_stdout(output):
                code = main([])
        self.assertEqual(code, 1)
        self.assertIsNone(json.loads(output.getvalue())["uptime"]["uptime_seconds"])

    def test_invalid_cli_format_returns_two_before_collection(self):
        error = StringIO()
        with patch(
            "linux_health_reporter.__main__.collect_snapshot",
            side_effect=AssertionError("collector must not run"),
        ):
            with contextlib.redirect_stderr(error):
                with self.assertRaises(SystemExit) as caught:
                    main(["--format", "xml"])
        self.assertEqual(caught.exception.code, 2)
        self.assertIn("invalid choice", error.getvalue())

    def test_help_returns_zero_before_collection(self):
        output = StringIO()
        with patch(
            "linux_health_reporter.__main__.collect_snapshot",
            side_effect=AssertionError("collector must not run"),
        ):
            with contextlib.redirect_stdout(output):
                with self.assertRaises(SystemExit) as caught:
                    main(["--help"])
        self.assertEqual(caught.exception.code, 0)
        self.assertIn("--format", output.getvalue())

    def test_empty_timestamp_cli_returns_one(self):
        snapshot = synthetic_snapshot()
        snapshot["timestamp_utc"] = ""
        output = StringIO()
        with patch("linux_health_reporter.__main__.collect_snapshot", return_value=snapshot):
            with contextlib.redirect_stdout(output):
                code = main([])
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(output.getvalue())["timestamp_utc"], "")


if __name__ == "__main__":
    unittest.main()
