# Linux Health Reporter

**A small, read-only Python CLI for basic Linux health snapshots.**

**Status:** v0.1.0 release candidate — prepared locally, not yet published.

Linux Health Reporter reads a fixed set of Linux metrics and prints a deterministic JSON or Markdown report to standard output. It is intentionally small, dependency-free at runtime and suitable for inspection and synthetic testing.

**This is not an AI agent or an autonomous monitoring service.** Its engineering workflow used AI-assisted implementation and independent second-model review; see [Engineering workflow](docs/engineering-workflow.md).

## Features

- 1-, 5- and 15-minute load averages from `/proc/loadavg`.
- Total and available RAM from `/proc/meminfo`.
- Total and unprivileged-available space on the root filesystem via `os.statvfs("/")`.
- Uptime from `/proc/uptime`.
- UTC timestamp in `YYYY-MM-DDTHH:MM:SSZ` format, or `null` if unavailable.
- JSON output by default, with an optional Markdown report.

**Requirements:** Linux and Python 3.10 or newer. Runtime dependencies: Python standard library only. Python 3.10 and 3.11 are declared compatibility targets, not yet runtime-tested.

## Quick start

From the project directory:

    python3 -B -m linux_health_reporter
    python3 -B -m linux_health_reporter --format json
    python3 -B -m linux_health_reporter --format markdown
    python3 -B -m linux_health_reporter --help

No installation is required for these commands. The `-B` option disables Python bytecode-cache writes. Without `-B`, Python may create `__pycache__` even though the reporter does not persist its own results.

Reports are sent to stdout; redirecting them to a file is an explicit user choice.

**Exit codes:** `0` = complete snapshot; `1` = timestamp or at least one metric unavailable; `2` = invalid command-line arguments.

## Output and interpretation

Every metric contains a `status` field of `ok` or `unavailable`. Unavailable measurements are reported as `null`, never silently replaced with zero. A missing or timezone-unaware timestamp is also `null`.

See [examples/sample.json](examples/sample.json). **All example values are synthetic**, not collected from an actual host.

Load average is **not** CPU utilization. The disk metric refers only to the filesystem containing `/`, and available space means space reported as available to an unprivileged user.

## Privacy and operational boundaries

- No elevated privileges, shell commands, network calls, agents, service control, background jobs or collection scheduling.
- Fixed collection targets; there are no user-specified filesystem paths.
- No hostname, user identifiers, IP/MAC addresses, process lists, device serial numbers, environment variables, logs or additional mounts in the report schema.
- Collection errors yield `unavailable` without exposing raw exception messages.
- Reports and timestamps may still reveal aspects of system use. **Review real reports before sharing them publicly.**

The project contains no source code, production telemetry or configuration copied from private projects.

## Tests and evidence

Run only the synthetic test suite:

    PYTHONDONTWRITEBYTECODE=1 python3 -B -m unittest discover -s tests -v

**Validated on 2026-10-30:** 37/37 synthetic tests passed on each of two Linux/KDE neon machines running Python 3.12.3. The same twelve pre-publication source files were checked with SHA256 on both machines; the second environment used an isolated temporary in-memory copy, removed after testing.

The tests inject synthetic `/proc`, disk and clock responses. They **do not execute the unmocked collector or validate live metrics**. Python 3.10 and 3.11 syntax was checked, but execution under those interpreters remains unverified. No deployment, performance, security-certification or production-availability claim is implied.

The separate model review identified a small backlog of non-blocking test-coverage and input-hardening notes; see [Engineering workflow](docs/engineering-workflow.md).

## Engineering provenance

This standalone portfolio tool was designed and supervised by **Fábio Folgado** with AI-assisted coding, human-authorized changes, synthetic regression tests and independent second-model review. The human owner defined the scope, evaluated the findings and approved each modification. The repository documents the process without asserting that the CLI itself is agentic.

See [Engineering workflow](docs/engineering-workflow.md) for the development and review approach, evidence boundaries and known limitations.

## License

Licensed under the [MIT License](LICENSE). Copyright (c) 2026 Fábio Folgado.

The runtime remains standard-library only. The build configuration declares `setuptools>=77` for modern project/license metadata; this is a **build-time**, not runtime, dependency.
