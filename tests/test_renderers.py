"""Renderers and CLI tests use injected fixtures only."""

import contextlib
from io import StringIO
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from linux_health_reporter import __version__
from linux_health_reporter.__main__ import main
from linux_health_reporter.renderers import render_json, render_markdown
from tests.test_collectors import synthetic_snapshot


class RendererTests(unittest.TestCase):
    def test_json_is_parseable_and_preserves_values(self):
        snapshot = synthetic_snapshot()
        text = render_json(snapshot)
        self.assertEqual(json.loads(text), snapshot)
        self.assertIn('"schema_version": "0.2"', text)

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
        self.assertIn("## Pressure stall information", text)

    def test_markdown_uses_human_readable_values(self):
        text = render_markdown(synthetic_snapshot())
        # 9437184000 B of 16777216000 B, swap 2040109056 of 2147483648 B,
        # disk 256000000000 of 512000000000 B, uptime 86400 s.
        expected_rows = (
            "| Load average (1m / 5m / 15m) | 0.42 / 0.36 / 0.31 |",
            "| Memory available | 8.8 GiB of 15.6 GiB (56.2 %) |",
            "| Swap free | 1.9 GiB of 2.0 GiB (95.0 %) |",
            "| Root filesystem available | 238.4 GiB of 476.8 GiB (50.0 %) |",
            "| Uptime | 1 d 00 h 00 min |",
            "| CPU | 1.25 / 0.80 / 0.40 % | n/a |",
            "| Memory | 0.50 / 0.25 / 0.10 % | 0.20 / 0.10 / 0.05 % |",
            "| I/O | 3.00 / 2.50 / 1.75 % | 1.50 / 1.25 / 0.75 % |",
        )
        for row in expected_rows:
            with self.subTest(row=row):
                self.assertIn(row, text)
        # Raw byte counts stay in JSON; Markdown shows the readable form only.
        self.assertNotIn("16777216000", text)

    def test_markdown_without_swap(self):
        snapshot = synthetic_snapshot()
        snapshot["swap"] = {"status": "ok", "total_bytes": 0, "free_bytes": 0}
        self.assertIn("| Swap free | No swap configured |", render_markdown(snapshot))

    def test_markdown_distinguishes_unsupported_from_unavailable(self):
        snapshot = synthetic_snapshot()
        snapshot["pressure"]["cpu"] = {"status": "unsupported", "some": None}
        snapshot["pressure"]["memory"] = {"status": "unsupported", "some": None, "full": None}
        snapshot["pressure"]["io"] = {"status": "unavailable", "some": None, "full": None}
        text = render_markdown(snapshot)
        self.assertIn("| CPU | Interface not exposed | n/a |", text)
        self.assertIn("| Memory | Interface not exposed | Interface not exposed |", text)
        self.assertIn("| I/O | Unavailable | Unavailable |", text)
        self.assertNotIn("None", text)

    def test_markdown_renders_huge_values_accepted_by_the_collector(self):
        # Review R-08: a corrupted but well-formed /proc/meminfo can yield
        # enormous integers; JSON and Markdown must both still render.
        from linux_health_reporter.collectors import collect_snapshot
        from tests.test_collectors import SYNTHETIC, synthetic_clock, synthetic_statvfs

        huge = 10 ** 398
        meminfo = f"MemTotal: {huge} kB\nMemAvailable: {huge} kB\nSwapTotal: {huge} kB\nSwapFree: 0 kB\n"
        source = dict(SYNTHETIC, **{"/proc/meminfo": meminfo})
        snapshot = collect_snapshot(
            read_text=lambda path: source[path], statvfs=synthetic_statvfs, clock=synthetic_clock
        )
        self.assertEqual(snapshot["memory"]["status"], "ok")
        self.assertIn("| Memory available |", render_markdown(snapshot))
        self.assertIn("(100.0 %)", render_markdown(snapshot))
        self.assertEqual(json.loads(render_json(snapshot))["memory"]["total_bytes"], huge * 1024)

    def test_markdown_tolerates_missing_pressure_section(self):
        snapshot = synthetic_snapshot()
        del snapshot["pressure"]
        text = render_markdown(snapshot)
        self.assertIn("| CPU | Unavailable | n/a |", text)
        self.assertIn("| I/O | Unavailable | Unavailable |", text)

    def test_unavailable_renders_without_raw_exception(self):
        snapshot = synthetic_snapshot()
        snapshot["memory"] = {
            "status": "unavailable",
            "total_bytes": None,
            "available_bytes": None,
        }
        rendered = render_markdown(snapshot)
        self.assertIn("| Memory available | Unavailable |", rendered)
        self.assertNotIn("None", rendered)


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

    def test_version_returns_zero_before_collection(self):
        output = StringIO()
        with patch(
            "linux_health_reporter.__main__.collect_snapshot",
            side_effect=AssertionError("collector must not run"),
        ):
            with contextlib.redirect_stdout(output):
                with self.assertRaises(SystemExit) as caught:
                    main(["--version"])
        self.assertEqual(caught.exception.code, 0)
        self.assertEqual(output.getvalue().strip(), f"linux-health-reporter {__version__}")

    def test_unsupported_pressure_keeps_exit_code_zero(self):
        snapshot = synthetic_snapshot()
        snapshot["pressure"] = {
            "cpu": {"status": "unsupported", "some": None},
            "memory": {"status": "unsupported", "some": None, "full": None},
            "io": {"status": "unsupported", "some": None, "full": None},
        }
        with patch("linux_health_reporter.__main__.collect_snapshot", return_value=snapshot):
            with contextlib.redirect_stdout(StringIO()):
                self.assertEqual(main([]), 0)

    def test_unavailable_pressure_or_swap_returns_one(self):
        cases = {
            "pressure": lambda s: s["pressure"].update(
                io={"status": "unavailable", "some": None, "full": None}
            ),
            "swap": lambda s: s.update(
                swap={"status": "unavailable", "total_bytes": None, "free_bytes": None}
            ),
        }
        for name, mutate in cases.items():
            with self.subTest(metric=name):
                snapshot = synthetic_snapshot()
                mutate(snapshot)
                with patch("linux_health_reporter.__main__.collect_snapshot", return_value=snapshot):
                    with contextlib.redirect_stdout(StringIO()):
                        self.assertEqual(main([]), 1)

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
