---
name: omni-sync
description: >-
  Generate a consolidated open-issues.md file as first-class agent context
  across GitHub.com, GitHub Enterprise Server "Helix", GitLab on cloud.gov,
  and GSA FedRAMP Jira. Also covers issue create/diff/sync commands, provider
  compatibility, body modes, and known failures. Use first when an agent needs
  current authored or assigned issue context across providers.
---

# omni-sync agent skill

`omni-sync` wraps the `gh`, `glab`, and `acli` CLIs as interchangeable issue
adapters driven by a canonical model. All CLI calls use argument lists (never
`shell=True`), so shell metacharacters in issue bodies are passed literally and
are safe.

## Primary Workflow: Build Agent Context

Run this before planning or changing work when current cross-provider issue
context is relevant:

```sh
mise exec -- uv run omni-sync board --output open-issues.md --body-limit 240
```

Treat `open-issues.md` as the single context artifact. It contains report time,
filters, totals, provider-specific Mermaid boards, linked issue details, and
provider failures. Read the entire file before selecting work; do not infer that
an absent issue is out of scope when the corresponding provider failed.

Interpret the exit status:

- `0`: all selected providers were queried successfully.
- `1`: the file was still written, but it contains partial results and explicit
  provider errors. Surface those errors and either fix configuration or narrow
  the query with `--target`.

Use filters to reduce context instead of post-processing provider output:

```sh
# Assigned work only
omni-sync board --relationship assigned

# A roster user across provider-specific usernames
omni-sync board --user person@agency.gov

# Security work in GitHub.com and Jira
omni-sync board --target gh-tts --target jira-mod \
  --label security --search "token rotation"

# Closed work for review
omni-sync board --state closed --limit 25
```

Available filters: repeatable `--relationship authored|assigned`, `--user
@me|email|username`, `--label`, and `--target`; plus `--state open|closed|all`,
`--search`, `--limit` (maximum 100), `--body-limit`, and `--output`.

Security boundary: `open-issues.md` is gitignored and may contain sensitive
provider content. Do not commit it or send it outside the authorized boundary.
The default `@me` query does not load `users.toml`; email filters load the local
roster to translate provider usernames and fail closed when a mapping is absent.

## Supported commands

| Command | Purpose |
|---|---|
| `omni-sync doctor` | Read-only: verify CLI install + auth, config parse, token presence. Run first. |
| `omni-sync preflight` | Read-only: verify each configured target exists, has issues enabled, and is writable. Run before create/sync. |
| `omni-sync create <title> <body> --to <target>...` | Create the same issue on 1+ targets. |
| `omni-sync board [filters]` | Write one consolidated Markdown issue-context file with provider boards and linked details. |
| `omni-sync pr <title> --base <b> --head <h> --to <target>...` | Open the same PR/MR across GitHub/GitLab targets (`--draft` supported). |
| `omni-sync diff <src> <src_id> <tgt> <tgt_id>` | Field-level diff between two issues. |
| `omni-sync sync <src> <src_id> <tgt> <tgt_id> --direction <dir> --body-mode <mode> [--apply]` | Reconcile drift one-directionally. |
| `omni-sync mirror [--to <name>...] [--apply]` | Push code to `[mirror]` remotes (HTTPS or SSH). |
| `omni-sync bench --target <t> --id <issue_id>` | Measure CLI invocation count + latency for a read (regression guard). |
| `omni-sync gh-jira sync-jira-from-github [--apply]` | Jira ← GitHub: labels, assignee, milestone-as-label, sync comment. |
| `omni-sync gh-jira backfill-github-from-jira [--apply]` | GitHub ← Jira: assignee backfill only, fail-closed. |

Targets: `gh-tts` (github.com), `gh-helix` (GHES), `gl-cg` (GitLab cloud.gov),
`jira-mod` (FedRAMP Jira). Repos/projects come from env vars (`GH_TTS_REPO`,
`GH_HELIX_REPO`, `GL_CG_REPO`, `JIRA_MOD_PROJECT`) or `.env`.

**Defaults are safe:** `sync` and the `gh-jira` commands default to `--dry-run`.
Pass `--apply` to write.

Batch commands are best-effort: they report all independent results, then exit
with code `1` if any target or ticket failed. Exit code `0` means the complete
requested batch succeeded.

`board` writes `open-issues.md` by default. The single artifact includes report
metadata, applied filters, totals, provider failures, separate GitHub.com,
GitHub Helix, GitLab, and Jira Mermaid Kanban blocks, and linked detail tables.
Filter with repeatable `--relationship`, `--user`, `--label`, and `--target`, or
with `--state`, `--search`, `--limit`, and `--body-limit`. Each board uses its
provider-specific configured issue URL so ticket links resolve directly.

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

## Label sync

`diff` and `sync` reconcile labels alongside title/body/state. On apply, the
source's labels are added to the target (`gh issue edit --add-label` /
`glab issue update --label`). Labels are additive — the sync does not delete
labels the target already has, so human-added labels on the target are
preserved. Label *order* never counts as a difference (sorted before compare).

## Assignees via identity map

`--assignee` on `create` and `pr` accepts an email (the pivot field) or a
username. Emails resolve per host through `users.toml` (gitignored):
`--assignee person@agency.gov --to gh-helix` → that host's login,
`--to gl-cg` → the GitLab login. A plain username passes through; an unmapped
email is skipped with a warning (never fails the command).

**Helix gotcha:** the SSO login handle is the `_gsagov`-suffixed SAML UID
(`<login>_gsagov`), but the GitHub login used for `--assignee` is the
un-suffixed `<login>`. The identity map stores the login; the `_gsagov` form
is only for the SSO sign-in prompt.

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
