---
name: omni-sync
description: >-
  Supported commands, provider CLI compatibility matrix, and known failures for
  the omni-sync harness (unified issue create/diff/sync across GitHub.com,
  GitHub Enterprise Server "Helix", GitLab on cloud.gov, and GSA FedRAMP Jira
  via acli). Use when running omni-sync, choosing a --body-mode, interpreting
  sync drift, or avoiding inputs that break a provider CLI.
---

# omni-sync agent skill

`omni-sync` wraps the `gh`, `glab`, and `acli` CLIs as interchangeable issue
adapters driven by a canonical model. All CLI calls use argument lists (never
`shell=True`), so shell metacharacters in issue bodies are passed literally and
are safe.

## Supported commands

| Command | Purpose |
|---|---|
| `omni-sync doctor` | Read-only: verify CLI install + auth, config parse, token presence. Run first. |
| `omni-sync preflight` | Read-only: verify each configured target exists, has issues enabled, and is writable. Run before create/sync. |
| `omni-sync create <title> <body> --to <target>...` | Create the same issue on 1+ targets. |
| `omni-sync diff <src> <src_id> <tgt> <tgt_id>` | Field-level diff between two issues. |
| `omni-sync sync <src> <src_id> <tgt> <tgt_id> --direction <dir> --body-mode <mode> [--apply]` | Reconcile drift one-directionally. |
| `omni-sync mirror [--to <name>...] [--apply]` | Push code to `[mirror]` remotes (HTTPS or SSH). |
| `omni-sync gh-jira sync-jira-from-github [--apply]` | Jira ← GitHub: labels, assignee, milestone-as-label, sync comment. |
| `omni-sync gh-jira backfill-github-from-jira [--apply]` | GitHub ← Jira: assignee backfill only, fail-closed. |

Targets: `gh-tts` (github.com), `gh-helix` (GHES), `gl-cg` (GitLab cloud.gov),
`jira-mod` (FedRAMP Jira). Repos/projects come from env vars (`GH_TTS_REPO`,
`GH_HELIX_REPO`, `GL_CG_REPO`, `JIRA_MOD_PROJECT`) or `.env`.

**Defaults are safe:** `sync` and the `gh-jira` commands default to `--dry-run`.
Pass `--apply` to write.

## `--body-mode` (sync)

How the source body is written onto the target issue:

| Mode | Effect | Use when |
|---|---|---|
| `replace` (default) | Overwrite the target body with the source body. | Source is the single source of truth. |
| `append` | Keep target body, append source below a `---` rule. | Preserving both sides' prose. |
| `comment` | Leave target body untouched; post source body as a new comment. | Target body is human-authored and must never be overwritten. |

`comment` mode mirrors the hard rule from the GitHub→Jira flow: **never
read-modify-write a human's description.** Prefer it when syncing into a
tracker whose descriptions people edit by hand.

## Auth is transport-agnostic

Commands behave identically whether `gh`/`glab` were authenticated via web
session or token, and whether `mirror` remotes are HTTPS (credential helper) or
SSH (agent/keychain). `mirror` only forces SSH `BatchMode` when you pass
`--batch` (for unattended runs).

## Provider CLI compatibility matrix

Verified live on 2026-10-07 by creating one issue per edge case and reading it
back (`harness/testing/live_probe.py`, corpus in
`harness/testing/edge_cases.py`). "OK" = body round-tripped byte-identical
after stripping the sync anchor.

| Edge case | gh (Helix) | glab (cloud.gov) | Notes |
|---|---|---|---|
| headings, bold/italic/code, links, images | OK | OK | |
| nested lists, ordered lists, task lists | OK | OK | |
| GFM tables | OK | OK | |
| fenced code (incl. quad-fence) | OK | OK | |
| blockquote, horizontal rule | OK | OK | `---` does not collide with the sync anchor footer. |
| HTML comments / forged `fed-sync-anchor` | OK | OK | Anchor parser isolates the footer; prose preserved. |
| backticks, `$()`, `${VAR}`, `&&`, `;`, `|`, `<` `>` | OK | OK | Passed literally — no shell interpretation. |
| quotes (single/double), backslashes | OK | OK | |
| leading dashes (`-x`, `--y`) | OK | OK | Sent as `--body` values, not parsed as flags. |
| unicode, emoji, RTL, em dash | OK | OK | |
| zero-width characters | OK | OK | Preserved verbatim. |
| tabs, trailing whitespace, very long lines | OK | OK | |
| Jira wiki markup, ADF-panel-like directives | OK | OK | Stored as literal text (not rendered). |
| YAML front matter, LaTeX math, footnotes, autolinks, escaped markdown | OK | OK | Stored verbatim; rendering differs by provider. |
| **CRLF line endings** | OK | **DRIFT** | GitLab normalizes `\r\n` → `\n`. See known failures. |
| **NUL byte in body** | **ERROR** | **ERROR** | Rejected before the CLI runs. See known failures. |

## See also

- `skills/omni-sync/known-failures.md` — the DRIFT/ERROR cases in detail, with
  causes and the recommended handling.
