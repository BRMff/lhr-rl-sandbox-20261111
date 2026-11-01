"""Swap parsing and collection tests. Synthetic inputs only."""

import unittest

from linux_health_reporter.collectors import has_unavailable, parse_meminfo, parse_swap
from tests.test_collectors import SYNTHETIC
from tests.test_pressure import snapshot_with

MEM = "MemTotal: 1024 kB\nMemAvailable: 512 kB\n"


class SwapParserTests(unittest.TestCase):
    def test_swap_totals_in_bytes(self):
        self.assertEqual(
            parse_swap(SYNTHETIC["/proc/meminfo"]),
            {"status": "ok", "total_bytes": 2147483648, "free_bytes": 2040109056},
        )

    def test_no_swap_configured_is_valid(self):
        self.assertEqual(
            parse_swap("SwapTotal: 0 kB\nSwapFree: 0 kB\n"),
            {"status": "ok", "total_bytes": 0, "free_bytes": 0},
        )

    def test_free_equal_total_is_valid(self):
        self.assertEqual(parse_swap("SwapTotal: 8 kB\nSwapFree: 8 kB\n")["free_bytes"], 8192)

    def test_rejects_inconsistent_input(self):
        cases = {
            "free above total": "SwapTotal: 8 kB\nSwapFree: 9 kB\n",
            "missing free": "SwapTotal: 8 kB\n",
            "missing total": "SwapFree: 8 kB\n",
            "duplicate": "SwapTotal: 8 kB\nSwapTotal: 8 kB\nSwapFree: 1 kB\n",
            "wrong unit": "SwapTotal: 8 MB\nSwapFree: 1 kB\n",
            "negative": "SwapTotal: -8 kB\nSwapFree: 1 kB\n",
            "not a number": "SwapTotal: lots kB\nSwapFree: 1 kB\n",
        }
        for name, text in cases.items():
            with self.subTest(case=name), self.assertRaises(ValueError):
                parse_swap(text)

    def test_swap_fields_do_not_affect_memory_parser(self):
        text = MEM + "SwapTotal: 8 MB\n"  # malformed swap line
        self.assertEqual(parse_meminfo(text)["status"], "ok")

    def test_ignores_other_swap_lines(self):
        text = "SwapCached: 99 kB\nSwapTotal: 8 kB\nSwapFree: 4 kB\nZswap: 1 kB\n"
        self.assertEqual(parse_swap(text)["free_bytes"], 4096)


class SwapCollectionTests(unittest.TestCase):
    def test_corrupted_swap_does_not_invalidate_memory(self):
        result = snapshot_with({"/proc/meminfo": MEM + "SwapTotal: 8 kB\nSwapFree: 9 kB\n"})
        self.assertEqual(result["memory"]["status"], "ok")
        self.assertEqual(
            result["swap"], {"status": "unavailable", "total_bytes": None, "free_bytes": None}
        )
        self.assertTrue(has_unavailable(result))

    def test_corrupted_memory_does_not_invalidate_swap(self):
        result = snapshot_with(
            {"/proc/meminfo": "MemTotal: 10 kB\nMemAvailable: 99 kB\nSwapTotal: 8 kB\nSwapFree: 4 kB\n"}
        )
        self.assertEqual(result["memory"]["status"], "unavailable")
        self.assertEqual(result["swap"]["status"], "ok")

    def test_unreadable_meminfo_makes_both_unavailable(self):
        result = snapshot_with({"/proc/meminfo": PermissionError("synthetic-secret")})
        self.assertEqual(result["memory"]["status"], "unavailable")
        self.assertEqual(result["swap"]["status"], "unavailable")
        self.assertNotIn("synthetic-secret", repr(result))

    def test_proc_swaps_is_never_read(self):
        reads = []

        def reader(path):
            reads.append(path)
            if path == "/proc/swaps":
                raise AssertionError("/proc/swaps exposes device names and paths")
            return SYNTHETIC[path]

        from linux_health_reporter.collectors import collect_snapshot
        from tests.test_collectors import synthetic_clock, synthetic_statvfs

        collect_snapshot(read_text=reader, statvfs=synthetic_statvfs, clock=synthetic_clock)
        self.assertNotIn("/proc/swaps", reads)
        self.assertEqual(reads.count("/proc/meminfo"), 1)


if __name__ == "__main__":
    unittest.main()
