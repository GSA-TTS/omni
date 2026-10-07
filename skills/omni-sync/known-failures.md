# omni-sync known failures

Curated from the live edge-case probe (2026-10-07,
`harness/testing/live_probe.py` over `harness/testing/edge_cases.py`) against
`gh` on github.helix.gsa.gov and `glab` on workshop.cloud.gov. Each entry is a
real, reproduced behavior — treat these as the ground truth over any assumption.

---

## 1. NUL byte in issue body — hard ERROR (all providers)

**Case:** `null_byteish` — a body containing `\x00`.

**Behavior:** fails before the CLI even runs. Python's `subprocess` rejects an
argument containing an embedded NUL (`ValueError: embedded null byte`), so both
`gh` and `glab` paths error out.

**Cause:** NUL is not a legal character in a process argument on POSIX; it also
is not valid in GitHub/GitLab issue bodies.

**Handling:** strip or reject `\x00` at the boundary before building a
`CanonicalIssue`. Do not attempt to escape it. This is a validate-at-the-edge
case, not a provider bug.

---

## 2. CRLF line endings — DRIFT on GitLab

**Case:** `crlf` — a body using `\r\n` line separators.

**Behavior:**
- `gh` (GitHub/GHES): round-trips `\r\n` unchanged → OK.
- `glab` (GitLab): the stored description comes back with `\n` only → DRIFT
  (the `\r` characters are dropped by GitLab server-side normalization).

**Cause:** GitLab normalizes description line endings to LF on write. This is a
server behavior, not a `glab` or omni-sync bug.

**Handling (fixed):** `compute_diff` now normalizes `\r\n` → `\n` on both sides
before comparing bodies, so a pure line-ending difference no longer registers as
drift and `sync` cannot oscillate on it. The raw `crlf` probe still shows DRIFT
on round-trip (GitLab really does drop the `\r`), but the diff engine treats the
two forms as equal.

---

## 3. Jira description must never be written (design invariant, not a probe case)

Carried over from the GitHub→Jira sync tooling: an earlier version wrote the
sync block into `fields.description` by round-tripping ADF through plain text,
which flattened rich formatting on ~82 real tickets on 2026-09-21.

**Rule:** the `acli` Jira adapter never reads or writes `description`. Sync
state lives in a dedicated, marker-identified **comment**. When syncing *into*
any tracker whose descriptions are human-authored, use `--body-mode comment`.

---

## 4. `acli` cannot set Sprint / Fix Version

`acli jira workitem edit` only writes `summary`, `description`, `type`,
`assignee`, and `labels`. There is no flag for Sprint or Fix Version/s.

**Handling:** GitHub milestones are encoded as prefixed Jira **labels**
(`milestone:PI-6-Iteration-6.1`). Native Sprint assignment requires the Agile
REST API with the board's Sprint custom field — outside `acli`'s scope.

---

## 5. GitLab issue state flags

`glab issue update` has **no** `--close` / `--reopen` flags (an early version
assumed it did and failed at runtime). State changes use the dedicated
subcommands `glab issue close` / `glab issue reopen`. `reopen` on an
already-open issue is a safe no-op.

---

## 6. PR/MR creation is interactive by default — `glab mr create` needs `--yes`

`gh pr create` opens the PR non-interactively once `--title`, `--body`,
`--base`, and `--head` are supplied. `glab mr create`, however, still prompts
(for push, remove-source-branch, etc.) unless you pass `--yes`. The GitLab
adapter always passes `--yes` so `omni-sync pr` never blocks waiting for input.

Flag mapping handled by the adapters:

| Concept | gh | glab |
|---|---|---|
| source branch | `--head` | `--source-branch` |
| target branch | `--base` | `--target-branch` |
| description | `--body` | `--description` |
| non-interactive | (default) | `--yes` |
| draft | `--draft` | `--draft` |

Jira has no PR/MR concept; `JiraAdapter.create_pull_request` raises
`AdapterError("...does not support pull requests")` — handle per-target, not
globally.

---

## General safety notes (verified OK, documented so they are not re-feared)

- Shell metacharacters (`` ` ``, `$()`, `${}`, `&&`, `;`, `|`, `<`, `>`),
  quotes, backslashes, and **leading dashes** are all safe: every CLI call uses
  an argument list (never `shell=True`), so values are passed literally and are
  never parsed as flags or expanded by a shell.
- Unicode, emoji, RTL text, and zero-width characters round-trip on both
  providers.
- A user body that forges the `fed-sync-anchor` footer is parsed as an anchor,
  but stripping it never devours surrounding real prose (covered by
  `tests/test_edge_cases.py`).
