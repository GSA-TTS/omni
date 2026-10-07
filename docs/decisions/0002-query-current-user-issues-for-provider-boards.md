---
title: "Query current-user issues for provider boards"
description: "Define the read-only cross-provider issue query and Mermaid board rendering contract."
status: "proposed"
tier: 2
date: "2026-10-07"
last_updated: "2026-10-07"
decision_makers: ["Project maintainers"]
category: "data handling"
nist_controls: ["AC-3", "AC-6", "SI-10", "SI-15"]
impact_level: "moderate"
ato_relevance: "yes-internal"
risk_treatment: "mitigate"
---

# Query current-user issues for provider boards

## Context and Problem Statement

Users need one read-only command that summarizes their open work across four
authenticated issue trackers. Mermaid Kanban supports one `ticketBaseUrl` per
diagram, while Omni must link cards to different provider hosts.

## Decision Drivers

- Queries must use the identity already authenticated by each provider CLI.
- The command must not require broader organization-wide read permissions.
- Issue text is external input and must not break generated Mermaid or Markdown.
- Every card must resolve to its provider's direct issue URL.
- One provider failure must not suppress results from independent providers.

## Considered Options

1. **One combined Mermaid board** - visually compact, but one global ticket URL
   cannot correctly link cards across four hosts.
2. **Four provider-specific Mermaid boards** - gives each board its own ticket
   URL while retaining a single generated report.
3. **Markdown table only** - supports links but omits the requested Kanban view.

## Decision Outcome

Chosen option: **Four provider-specific Mermaid boards**. Each adapter lists
open issues authored by or assigned to its authenticated current user. Results
are normalized, deduplicated per provider, escaped, truncated for cards, and
rendered with a direct-link details table below each board. Optional `[board]`
ticket-base URLs are authoritative when configured; otherwise safe defaults are
derived from the selected provider host and resource.

### Positive Consequences

- Cards link correctly across all configured hosts.
- Queries remain read-only and scoped to the authenticated user.
- Partial results remain available when one provider is unavailable.
- Deterministic sorting makes generated reports reviewable.

### Negative Consequences

- Authored and assigned queries can require two provider calls.
- Four diagrams are longer than one combined board.
- Provider CLI response formats remain an integration boundary requiring tests.

### Compliance Consequences

- Supports AC-3 and AC-6 by using existing authenticated identities and scoped
  read operations.
- Supports SI-10 and SI-15 by escaping provider-controlled issue content before
  rendering it in Mermaid and Markdown.
- Generated reports may contain issue content and must be handled according to
  the source systems' data classification.

## Links

- [Issue #8](https://github.com/GSA-TTS/omni/issues/8)
- [`harness/engine/board.py`](../../harness/engine/board.py)
