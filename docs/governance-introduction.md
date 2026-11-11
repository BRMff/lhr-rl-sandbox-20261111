# Gate introduction record

> **SANDBOX REPLAY (RL-E).** This repository, `BRMff/lhr-rl-sandbox-20261111`, is a
> disposable sandbox that replays the history of `BRMff/linux-health-reporter` to validate
> the release gate end to end. This file is **not** a governance record of the production
> repository and has no value outside this sandbox.
>
> The independent review named below was performed in the production context, on the
> same commit that is the head of pull request #4 here
> (`7524f6d3dde0d5996799f49a1ca4b3b179068967`). It is not a new review of this sandbox.
> The owner authorisation named below is the sandbox's own: it authorised the
> reconstruction of this history, including the merge of pull request #4 here.

This file records the out-of-band review and owner authorisation of pull request #4,
which introduced the review gate and the release gate. That pull request could not carry
a `review-gate` status, because the reconciler only runs from `main`. The release gate
accepts its merge only when the values below match the repository history
(see [release-process.md](release-process.md#gate-introduction-pr-4)).

The record is declared by the same GitHub identity that owns the repository. It documents
the review and the authorisation; it does not prove them.

## Validated values

The five lines below are read by `ci/release_gate.py`. Each key must appear exactly once
in this file.

```text
gate-introduction-pr: 4
head-sha: 7524f6d3dde0d5996799f49a1ca4b3b179068967
merge-commit-sha: d13046ccc3a49c6eb7ed2d62dd527f0f6379f630
independent-review: LHR-GOV-PR4-R3 = PASS_NARROW
owner-authorization: LHR-RL-E-F0 = AUTHORIZED_SANDBOX_ONLY
```

## Context (not validated)

- The merge commit has `dea0ac9379cc688b3ff9edce16f17bf41c29d747` (`GATE_BASELINE`) as
  its first parent and the final head of pull request #4 as its second parent.
- In this sandbox, pull request #4 was opened and merged as part of the replay; its
  head and base are the same commits as in production.
