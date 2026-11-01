# Changelog

All notable changes to this project are documented here.
The JSON schema is described in [docs/schema.md](docs/schema.md).

## [0.2.0] — 2026-11-01

### Added
- `swap` metric (`total_bytes`, `free_bytes`) from `/proc/meminfo`. A system
  without swap reports `ok` with zeros.
- `pressure` metric with PSI averages (`avg10`, `avg60`, `avg300`) for CPU
  (`some`), memory and I/O (`some`, `full`).
- `unsupported` status, used only in `pressure.*` when the kernel does not
  expose the interface. It does not change the exit code.
- `--version` option.
- `docs/schema.md`: the JSON contract, status values and exit codes.
- CI: Python 3.13 and 3.14, and a job that builds the sdist and wheel,
  installs the wheel in a clean environment and smoke-tests the CLI without
  collecting data from the CI runner.
- CI supply chain: GitHub Actions pinned by full commit SHA; build tools
  installed only from `ci/requirements-build.txt` (exact versions, wheel
  hashes, `--require-hashes --only-binary :all:`) in a dedicated build
  environment, with `python -m build --no-isolation`; weekly Dependabot
  update proposals for both, never merged automatically.

### Changed
- JSON `schema_version` is `"0.2"`. All 0.1 keys keep their name, type, unit,
  meaning and order; new keys are appended after `uptime`.
- Markdown output uses readable units (GiB, percentages, days/hours/minutes)
  and includes a PSI table. Markdown is a presentation format, not a contract:
  scripts that parsed the 0.1 Markdown table must switch to JSON.
- Markdown labels PSI blocks marked `unsupported` as "Interface not exposed"
  (the cause can be the kernel or the runtime). Byte values use integer
  arithmetic with tenths rounded half up.
- `/proc/meminfo` is read once and parsed independently for memory and swap.
- The CPU PSI `full` line is skipped before validation, so it can never make
  CPU pressure `unavailable`.
- The package version has a single source (`linux_health_reporter.__version__`).

### Unchanged
- The timestamp is still taken before any metric source is read, as in 0.1.
- Read-only, standard-library-only runtime; no shell, network, services or
  writes.
- Exit codes `0`, `1` and `2` keep their meaning.
- No host identifiers, paths or raw exception messages in reports.

## [0.1.0] — 2026-10-30

- First public release: load average, memory, root filesystem and uptime in
  JSON or Markdown.
