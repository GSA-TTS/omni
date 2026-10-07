---
title: "Mirror exact commits with fail-closed destinations"
description: "Define provenance and destination-history safeguards for cross-forge Git mirroring."
status: "proposed"
tier: 2
date: "2026-10-07"
last_updated: "2026-10-07"
decision_makers: ["Project maintainers"]
category: "deployment"
nist_controls: ["CM-3", "CM-5", "SA-10", "SI-7"]
impact_level: "moderate"
ato_relevance: "yes-internal"
risk_treatment: "mitigate"
---

# Mirror exact commits with fail-closed destinations

## Context and Problem Statement

A live mirror from a detached submodule checkout passed `--ref main`. Git
resolved the stale local `main` branch rather than checked-out `HEAD`, causing
the wrong ancestor commit to be pushed. A second destination had unrelated
protected history that could not safely be overwritten.

## Decision Drivers

- Dry-run output must identify the exact source object and destination ref.
- Detached checkouts and stale local branches must not create provenance drift.
- Existing or protected destination history must fail closed by default.
- Mirroring from another repository must not depend on Omni project discovery
  or modify the source repository's local remotes.

## Considered Options

1. **Continue pushing branch names** - simple but branch/worktree state can
   resolve to an unintended commit.
2. **Push resolved commit SHAs** - deterministic and reviewable, while retaining
   normal non-force Git fast-forward checks.
3. **Use `git push --mirror`** - copies every ref and can overwrite or expose
   refs that were not approved for publication.

## Decision Outcome

Chosen option: **Push resolved commit SHAs**. `mirror` defaults to checked-out
`HEAD`, validates repository connectivity, and pushes
`SHA:refs/heads/<destination>`. A source different from `HEAD` and an existing
destination branch each require separate explicit overrides. Inline `NAME=URL`
remotes and `--repository` support execution from a standalone binary without
altering local Git remote configuration.

### Positive Consequences

- Dry runs expose the exact source SHA before every push.
- Detached checkout state cannot silently select a stale local branch.
- Existing protected or unrelated history is preserved by default.
- Review branches provide a safe reconciliation path across unrelated histories.

### Negative Consequences

- Routine updates to an existing mirror require `--allow-existing` after review.
- Historical/non-HEAD mirroring requires `--allow-non-head`.
- Repository provisioning and PR/MR creation remain separate operations.

### Compliance Consequences

- Supports CM-3 and CM-5 by requiring explicit approval for higher-risk source
  and destination states.
- Supports SA-10 and SI-7 by preserving source provenance and object integrity.
- Repository creation, visibility, and access-control changes remain governed by
  a separate provisioning decision and issue.

## Links

- [Issue #28](https://github.com/GSA-TTS/omni/issues/28)
- [`harness/engine/mirror.py`](../../harness/engine/mirror.py)
