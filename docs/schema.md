# JSON report schema

The JSON output is the structured, versioned interface of Linux Health Reporter.
This document describes **schema version `0.2`**.

Markdown output is a presentation format for people. Its layout, labels and
units may change between versions and must not be parsed by scripts.

## Compatibility policy

- Changes within the `0.x` series are **additive**: existing keys keep their
  name, type, unit, meaning and position. New keys are appended.
- Consumers should read keys by name and ignore keys they do not know.
- `schema_version` changes whenever the schema changes.

## Top level

| Key | Type | Since | Description |
| --- | --- | --- | --- |
| `schema_version` | string | 0.1 | `"0.2"` |
| `timestamp_utc` | string or `null` | 0.1 | Start of collection (taken before any source is read), `YYYY-MM-DDTHH:MM:SSZ`. `null` if the clock was unavailable or not timezone-aware. |
| `load_average` | object | 0.1 | See below. |
| `memory` | object | 0.1 | See below. |
| `disk_root` | object | 0.1 | See below. |
| `uptime` | object | 0.1 | See below. |
| `swap` | object | 0.2 | See below. |
| `pressure` | object | 0.2 | Pressure stall information (PSI). |

## Status values

Every metric object has a `status` field.

| Status | Meaning | Used by | Exit code effect |
| --- | --- | --- | --- |
| `ok` | All fields hold valid measurements. | all metrics | none |
| `unavailable` | Collection failed: read error, permission denied or invalid data. All other fields are `null`, never zero. | all metrics | exit code `1` |
| `unsupported` | The kernel does not expose this PSI interface here. All other fields are `null`. | `pressure.*` only | none |

No reason, path or exception message is ever included.

## Metrics

| Object | Fields | Unit | Source |
| --- | --- | --- | --- |
| `load_average` | `1m`, `5m`, `15m` | number ≥ 0 | `/proc/loadavg` |
| `memory` | `total_bytes`, `available_bytes` | integer bytes | `/proc/meminfo` (`MemTotal`, `MemAvailable`) |
| `disk_root` | `total_bytes`, `available_bytes` | integer bytes | `statvfs("/")`, unprivileged available blocks |
| `uptime` | `uptime_seconds` | integer seconds (truncated) | `/proc/uptime` |
| `swap` | `total_bytes`, `free_bytes` | integer bytes | `/proc/meminfo` (`SwapTotal`, `SwapFree`) |

Invariants when `status` is `ok`: `memory` and `disk_root` have
`total_bytes > 0` and `available_bytes ≤ total_bytes`; `swap` has
`free_bytes ≤ total_bytes`. A system without swap reports
`{"status": "ok", "total_bytes": 0, "free_bytes": 0}`.

`/proc/swaps` is never read: it exposes device names and swap-file paths.

## Pressure (PSI)

```json
"pressure": {
  "cpu":    {"status": "ok", "some": {"avg10": 1.25, "avg60": 0.8, "avg300": 0.4}},
  "memory": {"status": "ok", "some": {...}, "full": {...}},
  "io":     {"status": "unsupported", "some": null, "full": null}
}
```

| Key | Lines | Source |
| --- | --- | --- |
| `cpu` | `some` | `/proc/pressure/cpu` |
| `memory` | `some`, `full` | `/proc/pressure/memory` |
| `io` | `some`, `full` | `/proc/pressure/io` |

- Each line is an object with `avg10`, `avg60` and `avg300`: floats from
  0 to 100, the percentage of time tasks were stalled over 10, 60 and 300
  seconds. `some` means at least one task was stalled; `full` means all
  non-idle tasks were stalled at the same time.
- CPU `full` is not reported. At system level the kernel defines it as zero.
  The line is skipped before validation, so its content never affects `cpu`.
- The cumulative `total` counter is not reported.
- Each resource is collected independently.

### unsupported versus unavailable

| Observed condition | Status |
| --- | --- |
| The file does not exist (`ENOENT`): kernel without PSI, older than 4.20, or a runtime that does not provide `/proc/pressure` | `unsupported` |
| Reading returns `EOPNOTSUPP` (for example PSI disabled with `psi=0`) | `unsupported` |
| Permission denied (`EACCES`, `EPERM`), for example a security policy | `unavailable` |
| Any other read error | `unavailable` |
| Empty or malformed content, including a path masked with `/dev/null` | `unavailable` |

### Containers

Inside containers `/proc/meminfo` and `/proc/pressure/*` often describe the
**host**, not the container, unless the runtime virtualises them (for
example with LXCFS). The reporter does not detect this case; interpret values
accordingly.

## Exit codes

| Code | Meaning |
| --- | --- |
| `0` | Complete snapshot. PSI blocks marked `unsupported` still count as complete. |
| `1` | The timestamp or at least one applicable metric is `unavailable`. |
| `2` | Invalid command-line arguments (nothing is collected). |

## Changes from 0.1

- Added `swap` and `pressure`, after `uptime`.
- Added the `unsupported` status, reserved for `pressure.*`.
- `schema_version` is `"0.2"`. All 0.1 keys are unchanged.
- The Markdown layout now uses readable units; Markdown is not a contract.
