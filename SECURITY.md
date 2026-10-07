---
title: "Security Policy"
description: "omni-sync vulnerability disclosure policy and supported branch information"
status: canonical
tier: 1
last_updated: "2026-10-06"
---

# Security Policy

As a U.S. Government agency, the General Services Administration (GSA) takes
seriously our responsibility to protect the public's information, including
financial and personal information, from unwarranted disclosure. This applies
to GSA-authored open source software, including this package.

## Reporting a Vulnerability

Do not open a public GitHub issue for security vulnerabilities.

Software published by the U.S. General Services Administration (GSA)
is covered by the **GSA Vulnerability Disclosure Program (VDP)**.

See the [GSA Vulnerability Disclosure Policy](https://gsa.gov/vulnerability-disclosure-policy)
at <https://www.gsa.gov/vulnerability-disclosure-policy> for details including:

* How to submit a report if you believe you have discovered a vulnerability.
* GSA's coordinated disclosure policy.
* Information on how you may conduct security research on GSA developed
  software and systems.
* Important legal and policy guidance.

The GSA VDP is the authoritative reporting path for this repository. Maintainers triage repository-specific reports after they are received through that process and will coordinate fixes through private channels before public disclosure.

### Response Expectations

GSA's VDP governs acknowledgement, validation, remediation coordination, and disclosure timing. Do not include sensitive vulnerability details in GitHub issues, pull requests, commit messages, or public comments.

### Scope note

This repository is a Robot Framework automation library, not a hosted
service — it has no production endpoint and is not covered by the
GSA Bug Bounty program's per-domain scope (cloud.gov, login.gov, etc.).
Vulnerabilities specific to this library's code (e.g., a flaw in the
`redaction`/secret-masking logic that fails to mask a known token format)
should still be reported through the GSA VDP channel above.

## Supported Versions

Only `main` is supported for security updates.

| Version (Branch) | Supported          |
| ---------------- | ------------------ |
| main             | :white_check_mark: |
| other            | :x:                |