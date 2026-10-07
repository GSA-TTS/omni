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

This issue-board workflow is not a prerequisite for code-only mirroring. Do not
run `board` merely to push Git refs; it can fail on unrelated issue-provider
configuration and adds no source-provenance evidence.

## Bootstrap a Fresh Repository

Download the latest platform binary and `SHA256SUMS.txt` from
`GSA-TTS/omni`, verify its digest, then create all three config files without a
source checkout or installed Python:

```sh
gh release download --repo GSA-TTS/omni \
  --pattern 'omni-sync-*-aarch64-apple-darwin' \
  --pattern SHA256SUMS.txt
artifact="$(find . -maxdepth 1 -name 'omni-sync-*-aarch64-apple-darwin' -print -quit)"
expected="$(awk -v name="${artifact#./}" '$2 == name { print $1 }' SHA256SUMS.txt)"
test -n "$expected" && test "$(shasum -a 256 "$artifact" | awk '{print $1}')" = "$expected"
chmod +x omni-sync-*-aarch64-apple-darwin

./omni-sync-*-aarch64-apple-darwin init --directory . \
  --github-org GSA-TTS \
  --github-repo example-repo \
  --jira-project-key TEST
./omni-sync-*-aarch64-apple-darwin validate
```

For every schema field, repeat `--project PATH=TOML_VALUE`. Use `--user
EMAIL.FIELD=TOML_VALUE` and `--group SLUG.FIELD=TOML_VALUE` for roster data.
The command validates all generated TOML before writing. Existing files are
preserved unless `--force` is explicit. Never pass secrets on command lines;
populate the generated gitignored `.env` through an approved secret mechanism.

## Supported commands

| Command | Purpose |
|---|---|
| `omni-sync doctor` | Read-only: verify CLI install + auth, config parse, token presence. Run first. |
| `omni-sync preflight` | Read-only: verify each configured target exists, has issues enabled, and is writable. Run before create/sync. |
| `omni-sync create <title> <body> --to <target>...` | Create the same issue on 1+ targets. |
| `omni-sync board [filters]` | Write one consolidated Markdown issue-context file with provider boards and linked details. |
| `omni-sync init [flags]` | Create and validate `omni-project.toml`, `users.toml`, and `.env` in a fresh repository. |
| `omni-sync validate` | Validate project and roster TOML without contacting providers. |
| `omni-sync pr <title> --base <b> --head <h> --to <target>...` | Open the same PR/MR across GitHub/GitLab targets (`--draft` supported). |
| `omni-sync diff <src> <src_id> <tgt> <tgt_id>` | Field-level diff between two issues. |
| `omni-sync sync <src> <src_id> <tgt> <tgt_id> --direction <dir> --body-mode <mode> [--apply]` | Reconcile drift one-directionally. |
| `omni-sync mirror [--to <name>...] [--apply]` | Push code to `[mirror]` remotes (HTTPS or SSH). |
| `omni-sync bench --target <t> --id <issue_id>` | Measure CLI invocation count + latency for a read (regression guard). |
| `omni-sync gh-jira sync-jira-from-github [--apply]` | Jira ← GitHub: labels, assignee, milestone-as-label, sync comment. |
| `omni-sync gh-jira backfill-github-from-jira [--apply]` | GitHub ← Jira: assignee backfill only, fail-closed. |

Targets: `gh-tts` (github.com), `gh-helix` (GHES), `gl-cg` (GitLab cloud.gov),
`jira-mod` (FedRAMP Jira). Repos/projects come from env vars (`GH_TTS_REPO`,
`GH_HELIX_REPO`, `GL_CG_REPO`, `JIRA_MOD_PROJECT`) or `.env`. GitLab also uses
`[gitlab].host` and `[gitlab].project` as authoritative defaults; environment
values override them when set.

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

## Safely Mirror a Repository

Repository creation and protected-branch reconciliation are provisioning tasks,
not implicit `mirror` behavior. Obtain explicit approval before creating a
remote repository or pushing. Never force-push a non-empty destination.

Run Omni independently of the source repository:

```sh
# Preferred: verified standalone release binary
/path/to/omni-sync mirror --repository /path/to/source \
  --remote helix=git@github.helix.gsa.gov:org/repo.git \
  --source-ref HEAD --destination main --to helix --dry-run

# Source-checkout fallback
uv run --project /path/to/omni omni-sync mirror \
  --repository /path/to/source \
  --remote helix=git@github.helix.gsa.gov:org/repo.git \
  --source-ref HEAD --destination main --to helix --dry-run
```

Do not use `mise exec -- uv run omni-sync` from an unrelated checkout: mise can
provide `uv`, but `uv run` resolves the current project's dependencies and may
not contain Omni.

### Source provenance gate

1. Inspect `git -C <source> status --short --branch`, `HEAD`, and upstream.
2. Run `git -C <source> fsck --connectivity-only --no-dangling`.
3. Prefer `--source-ref HEAD`. Omni resolves it to a commit SHA and pushes the
   explicit `SHA:refs/heads/<destination>` refspec.
4. Read the dry-run output and compare the source SHA to the intended pin.
5. If a named local branch differs from checked-out `HEAD`, Omni refuses it
   unless `--allow-non-head` is explicit.

This prevents a detached checkout from accidentally pushing a stale local
`main`, which occurred during a live mirror session.

### Destination gate

Omni probes each destination branch before pushing. An existing branch is
refused by default. For an empty target, apply the reviewed dry run:

```sh
/path/to/omni-sync mirror --repository /path/to/source \
  --remote helix=git@github.helix.gsa.gov:org/repo.git \
  --source-ref HEAD --destination main --to helix --apply --batch
```

For a non-empty or protected target with unrelated history, push a review branch
instead of overwriting `main`, then open a human-reviewed PR/MR:

```sh
/path/to/omni-sync mirror --repository /path/to/source \
  --remote workshop=git@workshop.cloud.gov:group/repo.git \
  --source-ref HEAD --destination mirror/source-<short-sha> \
  --to workshop --apply --batch
```

Use `--allow-existing` only after comparing both histories and confirming a
normal non-force push is intended. Omni never adds or rewrites local Git remotes
for these inline URLs.

### Provider CLI compatibility and authentication

- GitHub Enterprise: `gh repo view` has no portable `--hostname` flag. Use
  `GH_HOST=github.helix.gsa.gov gh repo view org/repo` or
  `gh api --hostname github.helix.gsa.gov repos/org/repo`.
- GitLab: use `glab api --hostname workshop.cloud.gov ...`; do not rely on
  `glab auth status` without a host because it may inspect unrelated
  `gitlab.com` configuration. Some `glab` versions do not support `api --jq`;
  request JSON and pipe it to a local `jq` invocation when field selection is
  needed.
- Omni loads the selected config's sibling `.env` for Omni subprocesses. It
  does not export that file into later arbitrary shell commands. For an approved
  direct `glab` call, load the environment in that command's shell without
  printing token values, or configure host authentication in `glab`.
- A GitLab `404` can mean either a missing project or a token that cannot see
  the namespace. Verify authenticated `glab api user --hostname <host>` before
  attempting creation. A `401` is an authentication failure, not evidence that
  the project is absent. If project `permissions` is null, inspect only the
  authenticated user's effective membership/access level; do not dump the full
  member list because it contains account PII.
- Some namespaces declare a configuration repository as the source of truth for
  projects and roles. Follow that IaC/change-review path instead of direct API
  creation when present. A direct creation attempt returning “already taken” is
  not proof that the path is safe to overwrite; refetch it with valid auth.

After applying, verify `git ls-remote` returns the exact expected source SHA.
Set a remote default branch only after its branch exists. Preserve accidental or
legacy refs for audit unless deletion is separately approved.

Never place credentials in a mirror URL. Omni rejects scheme-based URLs with
embedded usernames/passwords; use the provider credential helper, SSH agent, or
approved environment-based CLI authentication instead.

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

Managed Jira comment updates also fail closed: `JIRA_COMMENT_AUTHOR` must match
the exact `author` string returned by `acli ... comment list --json`. A missing
or mismatched value prevents updates to an existing marked comment; it does not
prevent creation when no managed comment exists.

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
