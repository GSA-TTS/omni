---
title: "Use typed assignments for repository bootstrap"
description: "Define the noninteractive config-generation interface used by downloaded standalone binaries."
status: "proposed"
tier: 2
date: "2026-10-07"
last_updated: "2026-10-07"
decision_makers: ["Project maintainers"]
category: "data handling"
nist_controls: ["CM-2", "CM-6", "SI-10", "SC-28"]
impact_level: "moderate"
ato_relevance: "yes-internal"
risk_treatment: "mitigate"
---

# Use typed assignments for repository bootstrap

## Context and Problem Statement

An agent working in a fresh repository needs to download one verified binary
and create valid Omni configuration without this source checkout. A dedicated
CLI flag for every TOML field would duplicate the schemas and drift as fields
are added, while accepting secrets on command lines would expose them through
shell history and process listings.

## Decision Drivers

- One command must cover every field in the current project and roster schemas.
- Generated files must be validated before any file is written.
- The interface must be deterministic and noninteractive across platforms.
- Secrets and credentials must not be accepted as command-line values.

## Considered Options

1. **One CLI flag per schema field** - discoverable but duplicates schema logic
   and requires command changes for every new field.
2. **Typed TOML assignments** - compact, schema-complete, and preserves TOML
   booleans, integers, strings, arrays, and quoted map keys.
3. **Read JSON from standard input** - structured but less convenient for agent
   shell workflows and introduces a second public configuration format.

## Decision Outcome

Chosen option: **Typed TOML assignments**. Repeatable `--project`, `--user`, and
`--group` flags accept schema paths and TOML values. Omni generates all content
in memory, validates project and roster data, then writes the requested files.
`.env` is created from a secret-free template and secret values are populated
through an approved local mechanism after bootstrap.

### Positive Consequences

- The CLI can express every current schema field without bespoke flags.
- Generated arrays, booleans, integers, and quoted keys preserve their types.
- Invalid or cross-reference-breaking input fails before any write.
- Agents can bootstrap fresh repositories with the standalone release binary.

### Negative Consequences

- Callers must quote TOML values correctly for their shell.
- Generic assignments are less discoverable than individual domain flags.
- Adding required schema fields may require updating bootstrap commands.

### Compliance Consequences

- Supports CM-2 and CM-6 with deterministic, validated configuration creation.
- Supports SI-10 by parsing values as TOML and validating both schemas.
- Supports SC-28 by excluding secret values from command-line flags and keeping
  generated local configuration ignored by source control.

## Links

- [`schema/omni-project.schema.json`](../../schema/omni-project.schema.json)
- [`schema/users.schema.json`](../../schema/users.schema.json)
- [`harness/config_writer.py`](../../harness/config_writer.py)
