"""Formatting helper tests: precision, boundaries and invalid input."""

import unittest

from linux_health_reporter.units import (
    format_bytes,
    format_duration,
    format_percent,
    format_ratio_triplet,
)


class FormatBytesTests(unittest.TestCase):
    def test_boundaries(self):
        cases = {
            0: "0 B",
            1: "1 B",
            1023: "1023 B",
            1024: "1.0 KiB",
            1536: "1.5 KiB",
            1048575: "1.0 MiB",  # rounds to 1024.0 KiB, promoted
            1048576: "1.0 MiB",
            1073741824: "1.0 GiB",
            16777216000: "15.6 GiB",
            512000000000: "476.8 GiB",
            1099511627776: "1.0 TiB",
            2 ** 50: "1.0 PiB",
            2 ** 60: "1.0 EiB",
            2 ** 70: "1024.0 EiB",  # largest unit is not promoted further
            1280: "1.3 KiB",  # 1.25 KiB: tenths round half up
            1126: "1.1 KiB",  # 1.0996 KiB
        }
        for value, expected in cases.items():
            with self.subTest(value=value):
                self.assertEqual(format_bytes(value), expected)

    def test_huge_values_do_not_overflow(self):
        # Review R-08: integer arithmetic only; no float conversion.
        text = format_bytes(10 ** 400)
        self.assertTrue(text.endswith(" EiB"))
        self.assertTrue(text.startswith("8673617379884035"))

    def test_rejects_invalid_values(self):
        for value in (-1, 1.5, True, None, "1024", float("nan")):
            with self.subTest(value=repr(value)), self.assertRaises(ValueError):
                format_bytes(value)


class FormatDurationTests(unittest.TestCase):
    def test_values(self):
        cases = {
            0: "0 s",
            59: "59 s",
            60: "1 min",
            3599: "59 min",
            3600: "1 h 00 min",
            3661: "1 h 01 min",
            86399: "23 h 59 min",
            86400: "1 d 00 h 00 min",
            90061: "1 d 01 h 01 min",
            400 * 86400: "400 d 00 h 00 min",
        }
        for value, expected in cases.items():
            with self.subTest(value=value):
                self.assertEqual(format_duration(value), expected)

    def test_truncates_instead_of_rounding_up(self):
        self.assertEqual(format_duration(119), "1 min")

    def test_rejects_invalid_values(self):
        for value in (-1, 1.5, False, None):
            with self.subTest(value=repr(value)), self.assertRaises(ValueError):
                format_duration(value)


class FormatPercentTests(unittest.TestCase):
    def test_values(self):
        self.assertEqual(format_percent(0, 10), "0.0 %")
        self.assertEqual(format_percent(10, 10), "100.0 %")
        self.assertEqual(format_percent(1, 3), "33.3 %")
        self.assertEqual(format_percent(2, 3), "66.7 %")

    def test_rejects_invalid_operands(self):
        for part, total in ((1, 0), (0, 0), (11, 10), (-1, 10), (1.0, 10), (True, 10)):
            with self.subTest(part=part, total=total), self.assertRaises(ValueError):
                format_percent(part, total)


class FormatTripletTests(unittest.TestCase):
    def test_two_decimals_and_suffix(self):
        self.assertEqual(format_ratio_triplet((0.4, 1, 12.346)), "0.40 / 1.00 / 12.35")
        self.assertEqual(format_ratio_triplet((0.0, 0.0, 0.0), " %"), "0.00 / 0.00 / 0.00 %")

    def test_rejects_invalid_values(self):
        for values in ((1, 2), (1, 2, 3, 4), (1, 2, -1), (1, 2, float("inf")), (1, 2, "3"), (True, 1, 1)):
            with self.subTest(values=values), self.assertRaises(ValueError):
                format_ratio_triplet(values)


if __name__ == "__main__":
    unittest.main()
