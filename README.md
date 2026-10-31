# Linux Health Reporter

[![Python tests](https://github.com/BRMff/linux-health-reporter/actions/workflows/tests.yml/badge.svg?branch=main)](https://github.com/BRMff/linux-health-reporter/actions/workflows/tests.yml)

**A lightweight, read-only Python CLI for Linux health snapshots — in JSON or Markdown.**

Get a quick view of system load, memory, root filesystem space and uptime without deploying a monitoring service. Output is written to standard output, ready to inspect or use in scripts. The runtime uses only the Python standard library.

**Release:** [v0.1.0 (experimental)](https://github.com/BRMff/linux-health-reporter/releases/tag/v0.1.0) · **License:** [MIT](LICENSE)

## What it reports

| Metric | Source |
| --- | --- |
| Load average (1, 5 and 15 minutes) | `/proc/loadavg` |
| Total and available RAM | `/proc/meminfo` |
| Root filesystem capacity and available space | `os.statvfs("/")` |
| System uptime | `/proc/uptime` |
| UTC collection timestamp | Python clock |

- Choose **JSON** for scripts and **Markdown** for readable summaries.
- Each metric has an explicit `ok` or `unavailable` status; unavailable values are `null`, not invented zeros.
- The fixed report schema excludes hostnames, IP addresses, usernames, device identifiers and raw exception messages.
- Collection is read-only and does not start services, execute shell commands, contact a network or write reports to disk.

## Quick start

**Requirements:** Linux and Python 3.10 or newer.

From a terminal:

```bash
git clone https://github.com/BRMff/linux-health-reporter.git
cd linux-health-reporter
python3 -B -m linux_health_reporter --format json
python3 -B -m linux_health_reporter --format markdown
```

No package installation is needed. `-B` prevents Python bytecode-cache writes. The CLI itself prints to stdout; saving output is an explicit choice.

Exit codes: `0` = complete snapshot; `1` = one or more unavailable readings (including timestamp); `2` = invalid CLI arguments.

## Example output

Both examples below use the **same synthetic fixture**, not measurements taken from a real computer.

### JSON

```json
{
  "schema_version": "0.1",
  "timestamp_utc": "2026-01-02T03:04:05Z",
  "load_average": {
    "status": "ok",
    "1m": 0.42,
    "5m": 0.36,
    "15m": 0.31
  },
  "memory": {
    "status": "ok",
    "total_bytes": 16777216000,
    "available_bytes": 9437184000
  },
  "disk_root": {
    "status": "ok",
    "total_bytes": 512000000000,
    "available_bytes": 256000000000
  },
  "uptime": {
    "status": "ok",
    "uptime_seconds": 86400
  }
}
```

[View the versioned JSON fixture](examples/sample.json).

### Markdown

```text
# Linux Health Report

Generated (UTC): 2026-01-02T03:04:05Z

| Metric | Value |
| --- | --- |
| Load average (1m / 5m / 15m) | 0.42 / 0.36 / 0.31 |
| RAM total / available (bytes) | 16777216000 / 9437184000 |
| Root filesystem total / available (bytes) | 512000000000 / 256000000000 |
| Uptime (seconds) | 86400 |
```

## Testing and engineering

**CI:** GitHub Actions runs the 37 synthetic unit tests on Python **3.10, 3.11 and 3.12** (three successful jobs in the [initial matrix run](https://github.com/BRMff/linux-health-reporter/actions/runs/41246975792)).

Run the same synthetic tests locally:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -B -m unittest discover -s tests -v
```

This project was developed with **human-defined requirements and approvals, AI-assisted implementation, synthetic regression tests and a separate model review**. The application itself is a conventional CLI; it does not run an AI model.

Read the [engineering workflow and validation evidence](docs/engineering-workflow.md) for the review process, earlier cross-host verification, documented findings and their precise scope.

## Known limitations

- **Experimental utility**, not a production-certified monitoring system. Its first public release is `v0.1.0`.
- The 37 tests use injected synthetic `/proc`, filesystem and clock inputs. Passing on Python 3.10–3.12 demonstrates test-suite execution, **not** end-to-end validation of live system metrics, installation or distribution builds.
- Load average is not CPU utilisation. Filesystem capacity covers only the filesystem containing `/`, and available space is reported for an unprivileged user.
- There is no scheduler, daemon, network reporting or background monitoring.
- Even without identifying fields, real timestamps and measurements may reveal usage patterns. **Review reports before sharing them publicly.**

## License

[MIT License](LICENSE) · Copyright © 2026 Fábio Folgado.
