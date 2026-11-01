# Engineering Workflow: Human-Controlled AI-Assisted Development

## Purpose and boundaries

Linux Health Reporter is a small, read-only Linux CLI, **not** a multi-agent system. This document describes the human-directed, AI-assisted engineering workflow used to design, implement and review it. It is a portfolio example of engineering discipline and agent/tool governance, not evidence that the application autonomously operates agents.

The standalone code and synthetic fixtures were kept separate from private projects. Infrastructure identifiers, private telemetry, access details and internal source code are excluded from this public-facing documentation.

## Responsibilities

**Human owner — Fábio Folgado**
- Defined the intended behavior, privacy requirements, scope and acceptable outputs.
- Authorized individual implementation steps and cross-machine tests.
- Reviewed findings, decided which corrections to make and retained the final release decision.

**AI-assisted implementation**
- Helped draft source code, deterministic synthetic fixtures and regression tests.
- Operated within scoped, explicitly approved file changes.
- Produced reproducible evidence, including test results and file-integrity checks.

**Independent second-model review**
- Examined the implementation and test contracts separately from the coding assistant.
- Challenged assumptions with synthetic adversarial probes, including targeted mutations.
- Reported shortcomings and limitations for the human owner to reconcile.

Independence here means a different reviewing model and a separate review task. It does **not** mean a formal third-party audit or certified evaluation.

## Workflow

1. **Requirements:** define fixed collection targets, stdout-only reporting, error handling, and privacy constraints.
2. **Scope and approval:** allow writes only in the standalone project; do not grant agents general access to private services.
3. **Implementation:** keep runtime dependencies to Python's standard library, with injected readers and clocks for hermetic tests.
4. **Automated testing:** use synthetic content rather than live host measurements.
5. **Adversarial review:** inspect failure modes, identifier leakage, permissive schemas and negative-control quality.
6. **Correction and reconciliation:** fix bounded findings, re-run the suite and verify the exact changed-file inventory.
7. **Cross-environment checks:** compare the same SHA256-pinned sources and synthetic tests on two Linux machines.
8. **Human release gate:** perform licensing, public-content hygiene, attribution and final release approval separately.

This workflow is human-in-the-loop. AI-generated output is treated as material to verify, not automatically trusted.

## Reproduction

From the project root, run:

    PYTHONDONTWRITEBYTECODE=1 python3 -B -m unittest discover -s tests -v

Expected for v0.2.0: **94 passing tests**. (The v0.1.0 baseline was 37.)

Test inputs simulate `/proc`, `statvfs`, clocks and CLI collection through dependency injection or mocks. They are not live system-health readings.

### Evidence snapshot: v0.2.0 (2026-11-01, pre-merge)

- **94/94 synthetic tests** passed locally on Python 3.10, 3.11, 3.12, 3.13 and 3.14 (interpreters provided by `uv`), and from an extracted sdist.
- **12 deliberate code mutations** (for example: treating permission errors as `unsupported`, counting `unsupported` as a failure, accepting PSI values above 100, reporting CPU `full`, reading `/proc/swaps`, reordering v0.1 keys, leaking an exception message) were each detected by the suite.
- A **contract test** compares v0.2 output with the unmodified v0.1.0 sample: all v0.1 keys keep their values, types and order; only `schema_version` differs.
- Package build was reproduced locally with setuptools (sdist → wheel), installed in a clean virtual environment and smoke-tested (`--help`, `--version`, invalid arguments, synthetic import checks). The CI job repeats this with `python -m build` on GitHub-hosted runners.
- No collection was run against a real host for this evidence.

### Evidence snapshot: v0.1.0 (2026-10-30)

- **37/37 synthetic tests** passed on two Linux/KDE neon machines, both using Python 3.12.3.
- **12/12 files from the earlier P2 snapshot** matched across machines by SHA256. Ten unchanged code/test/example/.gitignore files remain part of the 14-file release tree; the P2 README.md and pyproject.toml were later changed during P3, and LICENSE plus this workflow document were added afterwards. The final 14-file tree was verified locally, **not** hash-compared cross-host.
- The second machine used a temporary RAM-backed copy with cleanup verified.
- Python 3.10, 3.11 and 3.12 source syntax was checked; **only 3.12.3 was execution-tested**.
- A separate AI-model reviewer reported **41 in-memory mutation probes**, of which **34 were detected and 7 survived**. Those figures describe one exploratory review, not a mutation-testing certification or a comprehensive security score.
- No live host-telemetry validation was performed in those synthetic test runs.

## Known limitations and follow-up work

- From the v0.1.0 review: three low-severity test-coverage gaps (independent proof of the `total_bytes > 0` rule, acceptance of memory available equal to total, and explicit negative tests for invalid metric status/non-null unavailable fields) and some informational notes on permissive parsing of injected text. The v0.2 privacy and PSI tests add negative cases for invalid statuses and non-null values in non-`ok` blocks; the remaining items stay open.
- Python 3.10–3.14 are exercised in CI. Python 3.10 reaches end of life in October 2026; dropping it is a separate, future decision.
- PSI and swap behaviour inside containers is covered by simulated scenarios only; real values may describe the host.
- The CLI has not been benchmarked or deployed as a production monitoring service.

These items should remain visible rather than being converted into claims of comprehensive coverage.

## Privacy, security and attribution

The report schema is deliberately limited to a small allowlist of numeric fields and an optional UTC timestamp; this reduces, but does not eliminate, disclosure risk. Real reports may still reveal usage patterns. The collector reads only an explicit allowlist of sources (enforced by a test); `/proc/swaps` is excluded because it contains device names and paths.

Project code and documentation may be reused under the [MIT License](../LICENSE). The copyright holder is Fábio Folgado. Development assistance from AI tools and a separate AI-model review are disclosed to distinguish human responsibility from AI-generated contributions.
