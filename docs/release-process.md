# Release process

Releases are tags `vX.Y.Z` created by the owner. The `release tags` ruleset makes them
immutable once created. GitHub **cannot** make tag creation conditional on checks, so this
process combines a preventive preflight with detection after the tag is created.
Governance limits are described in [governance.md](governance.md).

## 1. Before the tag (preventive)

1. Merge everything for the release through reviewed pull requests.
2. Wait until CI on the `main` head is green.
3. Run the **release-gate** workflow (`workflow_dispatch`) **from `main`** with:
   - `tag`: `vX.Y.Z`
   - `sha`: the exact 40-character SHA of the **current** `main` head
4. The `verify` job must pass every condition:

   | # | Condition |
   |---|---|
   | P1 | `sha` is the current `main` head |
   | P2 | the required CI checks succeeded on `sha` |
   | P3 | every PR merged since the previous tag had `review-gate: success` on its merged head (PRs merged before the gate existed are reported as pre-gate) |
   | P4 | the tag matches `__version__`, and `CHANGELOG.md` has a dated entry for that version |
   | P5 | the tag does not exist yet |

   The run also checks its own provenance: it must be dispatched from `main` and run the
   `main` version of the workflow.
5. The `record` job then writes the evidence status `release-preflight/<tag>` on `sha`,
   linked to the run. If `verify` fails, no evidence is recorded.
6. The **owner authorises** the release in writing. This step is procedural; GitHub cannot
   tell the owner apart from an agent using the same identity.
7. The owner creates the tag and release in the GitHub interface, with target = **the
   exact SHA**, not the branch name. Add the preflight run URL to the release notes.

## 2. After the tag (detection)

Pushing a `v*` tag runs **release-gate** on the tag:

| # | Condition |
|---|---|
| T1 | the tag exists and resolves to commit `C` (lightweight or annotated) |
| T2 | `C` is on the first-parent history of `main`; `main` may have moved on since |
| T3 | P2–P4 hold for `C` |
| T4 | a valid `release-preflight/<tag>` status exists on `C`: success, created by `github-actions[bot]`, linked to a successful `workflow_dispatch` run of `release-gate.yml` on `main` for `C` with the expected title, and created **before** the tag run. **Missing evidence is a failure**, never a warning |

The daily **release-audit** applies T1–T4 to every `v*` tag from `main`. It therefore also
catches a tag whose commit carries a modified or missing gate. Tags created before the
gate existed (`v0.1.0`, `v0.2.0`) are reported as pre-gate.

## 3. If a violation is detected

The gate cannot undo a publication: the tag is protected against deletion.

1. Mark the release with a warning in its notes and do not promote it.
2. Fix the cause.
3. Publish a new patch release through this process.

## What GitHub enforces and what stays procedural

| Property | Enforced? |
|---|---|
| Tags `v*` cannot be changed or deleted | Yes (ruleset) |
| Merges to `main` need the required checks | Yes (ruleset) |
| Run metadata and status creator and time cannot be edited | Yes (platform) |
| Tag creation only after a passing preflight | **No**: detected by T4 and the audit |
| Owner vs agent authorisation | **No**: procedural |
