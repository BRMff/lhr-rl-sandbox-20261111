"""PSI parsing and collection tests. Synthetic inputs only; never reads /proc."""

import errno
import unittest

from linux_health_reporter.collectors import (
    collect_snapshot,
    has_unavailable,
    parse_pressure,
)
from tests.test_collectors import (
    SYNTHETIC,
    synthetic_clock,
    synthetic_statvfs,
)

SECRET = "synthetic-private-context-7f3a"


def snapshot_with(overrides):
    """Collect with SYNTHETIC sources, replacing selected paths.

    Each override is either replacement text or an exception instance to raise.
    """

    def reader(path):
        if path in overrides:
            value = overrides[path]
            if isinstance(value, BaseException):
                raise value
            return value
        return SYNTHETIC[path]

    return collect_snapshot(read_text=reader, statvfs=synthetic_statvfs, clock=synthetic_clock)


def os_error(code):
    return OSError(code, f"{errno.errorcode[code]}: {SECRET}")


ALL_PSI = ("/proc/pressure/cpu", "/proc/pressure/memory", "/proc/pressure/io")


class PressureParserTests(unittest.TestCase):
    def test_cpu_reports_some_only_even_when_full_line_exists(self):
        result = parse_pressure(SYNTHETIC["/proc/pressure/cpu"], "cpu")
        self.assertEqual(
            result,
            {"status": "ok", "some": {"avg10": 1.25, "avg60": 0.8, "avg300": 0.4}},
        )

    def test_cpu_without_full_line_older_kernels(self):
        text = "some avg10=0.10 avg60=0.20 avg300=0.30 total=9\n"
        self.assertEqual(parse_pressure(text, "cpu")["some"]["avg300"], 0.3)

    def test_memory_and_io_report_some_and_full(self):
        for resource in ("memory", "io"):
            with self.subTest(resource=resource):
                result = parse_pressure(SYNTHETIC[f"/proc/pressure/{resource}"], resource)
                self.assertEqual(set(result), {"status", "some", "full"})
                self.assertEqual(set(result["full"]), {"avg10", "avg60", "avg300"})

    def test_boundaries_zero_and_hundred_are_valid(self):
        text = (
            "some avg10=0.00 avg60=100.00 avg300=100 total=1\n"
            "full avg10=0 avg60=0 avg300=0 total=0\n"
        )
        result = parse_pressure(text, "memory")
        self.assertEqual(result["some"], {"avg10": 0.0, "avg60": 100.0, "avg300": 100.0})

    def test_values_are_floats(self):
        text = "some avg10=1 avg60=2 avg300=3 total=1\n"
        result = parse_pressure(text, "cpu")
        self.assertTrue(all(type(v) is float for v in result["some"].values()))

    def test_ignores_total_unknown_fields_and_unknown_line_kinds(self):
        text = (
            "some avg10=1.00 avg60=1.00 avg300=1.00 total=5 avg900=7.00\n"
            "full avg10=0.50 avg60=0.50 avg300=0.50 total=x\n"
            "partial avg10=9.99\n"
            "\n"
        )
        result = parse_pressure(text, "io")
        self.assertEqual(result["full"]["avg10"], 0.5)
        self.assertNotIn("total", result["some"])
        self.assertNotIn("avg900", result["some"])

    def test_cpu_full_line_never_affects_cpu_some(self):
        # Review R-01: the CPU "full" line is skipped before any validation.
        some = "some avg10=1 avg60=2 avg300=3 total=10\n"
        cases = {
            "nan": "full avg10=nan avg60=0 avg300=0 total=0\n",
            "above 100": "full avg10=101 avg60=0 avg300=0 total=0\n",
            "garbage": "full this is not psi\n",
            "missing averages": "full total=0\n",
            "duplicate full": "full avg10=0 avg60=0 avg300=0\nfull avg10=0 avg60=0 avg300=0\n",
            "two malformed full": "full avg10=x\nfull =\n",
        }
        for name, full in cases.items():
            for text in (some + full, full + some):
                with self.subTest(case=name, order=text.split()[0]):
                    self.assertEqual(
                        parse_pressure(text, "cpu"),
                        {"status": "ok", "some": {"avg10": 1.0, "avg60": 2.0, "avg300": 3.0}},
                    )

    def test_memory_and_io_validate_full_line(self):
        some = "some avg10=1 avg60=1 avg300=1 total=1\n"
        cases = {
            "above 100": "full avg10=101 avg60=0 avg300=0 total=0\n",
            "nan": "full avg10=nan avg60=0 avg300=0 total=0\n",
            "negative": "full avg10=0 avg60=-1 avg300=0 total=0\n",
            "missing avg300": "full avg10=0 avg60=0 total=0\n",
            "duplicate full": "full avg10=0 avg60=0 avg300=0\nfull avg10=0 avg60=0 avg300=0\n",
        }
        for resource in ("memory", "io"):
            for name, full in cases.items():
                with self.subTest(resource=resource, case=name), self.assertRaises(ValueError):
                    parse_pressure(some + full, resource)

    def test_rejects_malformed_input(self):
        good_full = "full avg10=0.00 avg60=0.00 avg300=0.00 total=0\n"
        cases = {
            "empty": "",
            "missing some": good_full,
            "memory missing full": "some avg10=1 avg60=1 avg300=1 total=1\n",
            "duplicate some": "some avg10=1 avg60=1 avg300=1\nsome avg10=1 avg60=1 avg300=1\n" + good_full,
            "duplicate key": "some avg10=1 avg10=2 avg60=1 avg300=1\n" + good_full,
            "missing avg60": "some avg10=1 avg300=1 total=1\n" + good_full,
            "token without =": "some avg10=1 avg60 avg300=1\n" + good_full,
            "empty key": "some =1 avg10=1 avg60=1 avg300=1\n" + good_full,
            "above 100": "some avg10=100.01 avg60=1 avg300=1\n" + good_full,
            "negative": "some avg10=-0.01 avg60=1 avg300=1\n" + good_full,
            "nan": "some avg10=nan avg60=1 avg300=1\n" + good_full,
            "inf": "some avg10=inf avg60=1 avg300=1\n" + good_full,
            "not a number": "some avg10=high avg60=1 avg300=1\n" + good_full,
            "overflow": "some avg10=1e400 avg60=1 avg300=1\n" + good_full,
        }
        for name, text in cases.items():
            with self.subTest(case=name), self.assertRaises(ValueError):
                parse_pressure(text, "memory")


class PressureCollectionTests(unittest.TestCase):
    def test_complete_pressure_snapshot(self):
        result = snapshot_with({})
        self.assertEqual(
            {name: block["status"] for name, block in result["pressure"].items()},
            {"cpu": "ok", "memory": "ok", "io": "ok"},
        )
        self.assertFalse(has_unavailable(result))

    def test_missing_interface_is_unsupported_and_not_a_failure(self):
        result = snapshot_with({path: os_error(errno.ENOENT) for path in ALL_PSI})
        self.assertEqual(result["pressure"]["cpu"], {"status": "unsupported", "some": None})
        self.assertEqual(
            result["pressure"]["memory"],
            {"status": "unsupported", "some": None, "full": None},
        )
        self.assertFalse(has_unavailable(result))

    def test_eopnotsupp_is_unsupported(self):
        result = snapshot_with({"/proc/pressure/io": os_error(errno.EOPNOTSUPP)})
        self.assertEqual(result["pressure"]["io"]["status"], "unsupported")
        self.assertEqual(result["pressure"]["cpu"]["status"], "ok")
        self.assertFalse(has_unavailable(result))

    def test_file_not_found_subclass_is_unsupported(self):
        result = snapshot_with({"/proc/pressure/cpu": FileNotFoundError(errno.ENOENT, SECRET)})
        self.assertEqual(result["pressure"]["cpu"]["status"], "unsupported")

    def test_permission_errors_are_unavailable(self):
        for error in (
            PermissionError(errno.EACCES, SECRET),
            PermissionError(errno.EPERM, SECRET),
            os_error(errno.EACCES),
        ):
            with self.subTest(error=type(error).__name__):
                result = snapshot_with({"/proc/pressure/memory": error})
                self.assertEqual(
                    result["pressure"]["memory"],
                    {"status": "unavailable", "some": None, "full": None},
                )
                self.assertTrue(has_unavailable(result))

    def test_other_read_errors_are_unavailable(self):
        for error in (
            os_error(errno.EIO),
            os_error(errno.ENOTDIR),  # only ENOENT/EOPNOTSUPP mean "not exposed"
            NotADirectoryError(errno.ENOTDIR, SECRET),
            IsADirectoryError(errno.EISDIR, SECRET),
            OSError(SECRET),  # no errno at all
            UnicodeDecodeError("ascii", b"\xff", 0, 1, SECRET),
        ):
            with self.subTest(error=repr(error)[:40]):
                result = snapshot_with({"/proc/pressure/cpu": error})
                self.assertEqual(result["pressure"]["cpu"]["status"], "unavailable")
                self.assertTrue(has_unavailable(result))

    def test_invalid_content_is_unavailable(self):
        result = snapshot_with({"/proc/pressure/io": "some avg10=250 avg60=1 avg300=1\n"})
        self.assertEqual(result["pressure"]["io"]["status"], "unavailable")
        self.assertIsNone(result["pressure"]["io"]["some"])
        self.assertTrue(has_unavailable(result))

    def test_resources_are_independent(self):
        result = snapshot_with(
            {
                "/proc/pressure/cpu": os_error(errno.ENOENT),
                "/proc/pressure/memory": "garbage",
            }
        )
        statuses = {name: block["status"] for name, block in result["pressure"].items()}
        self.assertEqual(statuses, {"cpu": "unsupported", "memory": "unavailable", "io": "ok"})
        for metric in ("load_average", "memory", "disk_root", "uptime", "swap"):
            self.assertEqual(result[metric]["status"], "ok", metric)

    def test_errors_never_leak_into_snapshot(self):
        result = snapshot_with(
            {
                "/proc/pressure/cpu": os_error(errno.ENOENT),
                "/proc/pressure/memory": PermissionError(errno.EACCES, SECRET),
                "/proc/pressure/io": os_error(errno.EIO),
            }
        )
        self.assertNotIn(SECRET, repr(result))
        self.assertNotIn("/proc", repr(result))

    def test_has_unavailable_treats_unknown_or_missing_pressure_as_failure(self):
        cases = {
            "unknown status": lambda s: s["pressure"]["cpu"].update(status="error"),
            "missing cpu": lambda s: s["pressure"].pop("cpu"),
            "missing memory": lambda s: s["pressure"].pop("memory"),
            "missing io": lambda s: s["pressure"].pop("io"),
            "missing section": lambda s: s.pop("pressure"),
            "non-dict section": lambda s: s.update(pressure=None),
            # Review R-06: "ok" without a window object is not a valid block.
            "ok cpu with null some": lambda s: s["pressure"].update(cpu={"status": "ok", "some": None}),
            "ok io without full": lambda s: s["pressure"]["io"].pop("full"),
            "ok memory with scalar full": lambda s: s["pressure"]["memory"].update(full=0.0),
        }
        for name, mutate in cases.items():
            with self.subTest(case=name):
                result = snapshot_with({})
                mutate(result)
                self.assertTrue(has_unavailable(result))


class ContainerScenarioTests(unittest.TestCase):
    """Simulated container/runtime environments. The real behaviour depends on
    the kernel and runtime; these tests fix how each observable condition is
    classified. Values visible inside a container may describe the host."""

    def test_runtime_without_psi_interface(self):
        # e.g. sandboxed runtimes or kernels without CONFIG_PSI: no /proc/pressure.
        result = snapshot_with({path: FileNotFoundError(errno.ENOENT, SECRET) for path in ALL_PSI})
        self.assertTrue(all(b["status"] == "unsupported" for b in result["pressure"].values()))
        self.assertFalse(has_unavailable(result))

    def test_psi_disabled_at_boot_or_by_cgroup(self):
        # psi=0 or a cgroup interface that reports EOPNOTSUPP.
        result = snapshot_with({path: os_error(errno.EOPNOTSUPP) for path in ALL_PSI})
        self.assertTrue(all(b["status"] == "unsupported" for b in result["pressure"].values()))
        self.assertFalse(has_unavailable(result))

    def test_masked_proc_path_reads_empty(self):
        # Runtimes can mask /proc entries by bind-mounting /dev/null: the file
        # exists but is empty. That is invalid data, not a missing interface.
        result = snapshot_with({path: "" for path in ALL_PSI})
        self.assertTrue(all(b["status"] == "unavailable" for b in result["pressure"].values()))
        self.assertTrue(has_unavailable(result))

    def test_security_policy_denies_access(self):
        # e.g. an LSM/seccomp profile returning EACCES or EPERM.
        result = snapshot_with({path: PermissionError(errno.EPERM, SECRET) for path in ALL_PSI})
        self.assertTrue(all(b["status"] == "unavailable" for b in result["pressure"].values()))
        self.assertTrue(has_unavailable(result))

    def test_container_without_swap(self):
        meminfo = "MemTotal: 1024000 kB\nMemAvailable: 512000 kB\nSwapTotal: 0 kB\nSwapFree: 0 kB\n"
        result = snapshot_with({"/proc/meminfo": meminfo})
        self.assertEqual(result["swap"], {"status": "ok", "total_bytes": 0, "free_bytes": 0})
        self.assertFalse(has_unavailable(result))


if __name__ == "__main__":
    unittest.main()
