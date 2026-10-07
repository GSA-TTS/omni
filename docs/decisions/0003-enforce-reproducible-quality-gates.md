---
title: "Enforce reproducible quality and release gates"
description: "Record the pinned lint, type, coverage, dependency, and cross-platform release checks."
status: "proposed"
tier: 2
date: "2026-10-07"
last_updated: "2026-10-07"
decision_makers: ["Project maintainers"]
category: "dependency and supply chain"
nist_controls: ["CA-2", "SA-11", "SI-2", "SR-3"]
impact_level: "moderate"
ato_relevance: "yes-internal"
risk_treatment: "mitigate"
---

# Enforce reproducible quality and release gates

## Context and Problem Statement

The repository had tests and config validation but no enforced lint, type,
coverage, or dependency-vulnerability gates. PyApp release binaries also used
Python 3.12 while development used 3.13, did not bundle Python dependencies,
and depended on a first-run CPython download that could fail enterprise TLS
validation. Windows artifacts were not meaningfully smoke-tested.

## Decision Drivers

- Local and CI verification must use one reproducible command.
- Direct tooling dependencies must be pinned and locked.
- Coverage should prevent immediate regression without imposing an arbitrary
  aspirational threshold.
- Every published platform artifact must execute before release.

## Considered Options

1. **Keep tests as the only gate** - minimal maintenance, but misses static,
   dependency, and packaging defects.
2. **Use hosted third-party quality services** - rich reporting, but adds an
   external service and authorization boundary.
3. **Use pinned local tools in CI** - keeps checks reproducible and runnable in
   the existing development environment.

## Decision Outcome

Chosen option: **Use pinned local tools and standalone native artifacts**.
`make check` runs Ruff, mypy,
pytest with coverage, pip-audit, and zizmor. The initial coverage floor is 75%,
just below the measured 76% baseline. Development and standalone releases use
Python 3.13. PyInstaller bundles CPython, application dependencies, schemas, and
templates. Every release artifact initializes and validates a fresh repository
with proxy-aware outbound networking directed to an unavailable local endpoint.
All third-party actions use immutable commit SHAs with version comments. All
Linux CI and release jobs use Ubuntu 24.04 LTS instead of the mutable
`ubuntu-latest` label. Checkout credentials are not persisted, publishing write
permission is scoped to the release job, and runtime artifacts are published
with the runner-provided GitHub CLI.

### Positive Consequences

- Contributors and CI run the same verification command.
- Static and dependency failures block regressions before merge.
- Release runtime behavior is aligned across development and artifacts.
- Windows artifacts receive execution coverage before publication.
- First execution does not download CPython or Python dependencies.
- Published SHA-256 checksums support artifact verification before execution.
- Workflow dependencies are immutable and statically scanned.
- Linux runner migrations become explicit reviewable changes.

### Negative Consequences

- CI and local checks take longer and install additional development tools.
- Ruff and mypy configuration require maintenance as the codebase evolves.
- Action and runner updates require deliberate SHA/image updates.
- Coverage measures executed lines, not correctness or requirement coverage.

### Compliance Consequences

- Supports SA-11 and CA-2 with repeatable developer testing and evidence.
- Supports SI-2 and SR-3 through locked dependency vulnerability checks.
- Tool upgrades require normal dependency and license review.

## Links

- [Issue #8](https://github.com/GSA-TTS/omni/issues/8)
- [`Makefile`](../../Makefile)
- [CI workflow](../../.github/workflows/ci.yml)
- [Release workflow](../../.github/workflows/release.yml)
