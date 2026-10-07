---
title: "Use pinned dependencies for installed configuration validation"
description: "Record why omni-sync ships JSON Schemas and uses exact direct dependency versions."
status: "proposed"
tier: 2
date: "2026-10-07"
last_updated: "2026-10-07"
decision_makers: ["Project maintainers"]
category: "dependency and supply chain"
nist_controls: ["SA-11", "SI-10", "SR-3", "SR-11"]
impact_level: "moderate"
ato_relevance: "yes-internal"
risk_treatment: "mitigate"
---

# Use pinned dependencies for installed configuration validation

## Context and Problem Statement

Source checkouts validate configuration with committed JSON Schemas, but built
wheels previously omitted those schemas and treated `jsonschema` as a
development-only dependency. Installed clients therefore received weaker
validation and `omni-sync init` could not access its templates.

## Decision Drivers

- Installed and source-checkout behavior must be equivalent.
- Invalid external configuration must fail before provider writes occur.
- The committed schemas must remain the single source of truth for validation
  and editor integration.
- Runtime and development dependencies must use current, exact stable versions
  and be represented in `uv.lock`.

## Considered Options

1. **Use Pydantic models only** - provides typed validation but would duplicate
   or replace the existing public JSON Schema contract.
2. **Retain optional JSON Schema validation** - avoids runtime packages but
   silently weakens validation when `jsonschema` is unavailable.
3. **Ship schemas and pin jsonschema at runtime** - preserves the existing
   contract and gives every installation the same validation behavior.

## Decision Outcome

Chosen option: **Ship schemas and pin jsonschema at runtime**. The wheel includes
the canonical schemas and initialization templates as package resources.
`jsonschema==4.26.0` and all other direct dependencies use exact stable versions
recorded in `pyproject.toml` and `uv.lock`.

### Positive Consequences

- Installed clients receive the same full validation as development clients.
- Clean-wheel initialization no longer depends on repository-relative files.
- Schemas remain reusable by editors and external tooling.

### Negative Consequences

- The runtime installation includes `jsonschema` and its transitive packages.
- Dependency versions must be deliberately updated and revalidated.
- Hatch build mappings must remain synchronized with canonical root assets.

### Compliance Consequences

- Supports SA-11 and SI-10 by applying consistent validation before operations.
- Requires normal dependency vulnerability, license, and integrity review under
  SR-3 and SR-11 when the pinned version changes.
- Does not change the authorization boundary or introduce a network service.

## Links

- [Issue #8](https://github.com/GSA-TTS/omni/issues/8)
- [`pyproject.toml`](../../pyproject.toml)
- [`schema/`](../../schema/)
