# omni-sync

Unified CLI and synchronization harness across multi-tenant, FedRAMP-accredited
Git and issue-tracking environments: GitHub.com, GitHub Enterprise Server
(Helix), GitLab on cloud.gov, and Jira FedRAMP Moderate.

Provider CLIs (`gh`, `glab`, `jira-cli`) are treated as interchangeable
transport adapters driven by a canonical issue model, avoiding an M x N
conversion matrix between provider formats.

## Prerequisites

Managed via [mise](https://mise.jdx.dev/):

```sh
mise install
```

This provisions `gh`, `glab`, `jira-cli` (via aqua), and the Python/`uv`
toolchain, and sets default host env vars (`HELIX_GH_HOST`,
`CLOUDGOV_GLAB_HOST`, `JIRA_INSTANCE_URL`, `GITHUB_PUBLIC_HOST`).

Install the harness and dev dependencies:

```sh
uv sync
```

## Authentication

Copy the example env file and fill in the Jira API token (the only secret this
project reads from `.env`); `gh` and `glab` manage their own credentials:

```sh
cp .env.example .env
```

`.env` is gitignored — never commit real tokens.

### Jira (GSA FedRAMP GovCloud) — API token

The Atlassian GovCloud instance uses API-token auth. Create a token, then put
it in `.env`:

1. Open the GovCloud token manager:
   <https://id.atlassian-us-gov-mod.com/manage-profile/security/api-tokens>
2. Click **Create API token**, name it (e.g. `omni-sync`), and copy the value.
3. Set it in `.env`:
   ```sh
   JIRA_BASE_URL=https://gsa-standard.atlassian-us-gov-mod.net
   JIRA_EMAIL=your.name@gsa.gov
   JIRA_API_TOKEN=<paste token>
   ```

For the `acli`-based GitHub↔Jira flow, enable GovCloud mode once and log in
with the same token:

```sh
acli config gov-cloud --enable
echo "$JIRA_API_TOKEN" | acli jira auth login \
  --site "gsa-standard.atlassian-us-gov-mod.net" \
  --email "$JIRA_EMAIL" --token
acli jira auth status
```

### GitHub (`gh`) — SSH or `gh auth login`

Authenticate `gh` once per host. Either use the interactive login (selecting
SSH as the Git protocol when prompted):

```sh
# github.com
gh auth login

# GitHub Enterprise Server (Helix)
gh auth login --hostname github.helix.gsa.gov
```

> **Helix SSO login vs. username.** On `github.helix.gsa.gov` you sign in
> through SSO using the `_gsagov`-suffixed form of your handle (e.g.
> `<login>_gsagov`) to reach the correct SSO endpoint. That suffixed value is
> the SAML external UID, **not** your GitHub login. Your actual GitHub login on
> Helix (what `gh api user --jq .login` returns, and what `--assignee` expects)
> is the un-suffixed form (`<login>`). The identity map therefore stores the
> **login**, not the SSO form, since assignments resolve against the login —
> use the `_gsagov` value only at the SSO login prompt.

…or, if you already have SSH keys configured, authenticate the API with a token
while keeping SSH for Git operations:

```sh
gh auth login --git-protocol ssh --hostname github.com
gh auth status
```

> omni-sync is transport-agnostic: issue/sync commands call the authenticated
> `gh`/`glab` CLIs regardless of whether you logged in via a web session or a
> token, and `mirror` works with HTTPS (credential helper) or SSH remotes
> interchangeably. You do not need to standardize on one.

### GitLab (`glab`) — login options

`glab` on a self-managed/cloud.gov instance supports OAuth (web or device) and
personal access tokens. See the
[GitLab CLI auth docs](https://docs.gitlab.com/cli/authentication/).

```sh
# OAuth via local browser (requires an OAuth app registered on the instance)
glab config set client_id <CLIENT_ID> --host workshop.cloud.gov
glab auth login --hostname workshop.cloud.gov        # choose "Web"

# OAuth device flow for headless/SSH sessions (no local browser)
glab auth login --hostname workshop.cloud.gov --device

# Personal access token (scopes: api, write_repository) from a file
glab auth login --hostname workshop.cloud.gov --stdin < token.txt

# Verify
glab auth status
```

Token precedence: if `GITLAB_TOKEN` is set in the environment it overrides any
token stored by `glab auth login`.

## Configuration

Each target repo/project is resolved from an environment variable:

| Target     | System                          | Env var          |
|------------|----------------------------------|------------------|
| `gh-tts`   | github.com                       | `GH_TTS_REPO`    |
| `gh-helix` | github.helix.gsa.gov (GHES)      | `GH_HELIX_REPO`  |
| `gl-cg`    | workshop.cloud.gov (GitLab)      | `GL_CG_REPO`     |
| `jira-mod` | FedRAMP Moderate Jira project    | `JIRA_MOD_PROJECT` |

```sh
export GH_TTS_REPO=gsa-tts/core-repo
export GH_HELIX_REPO=org/repo
export GL_CG_REPO=group/project
export JIRA_MOD_PROJECT=PROJ
```

Each underlying CLI (`gh`, `glab`, `jira-cli`) must already be authenticated
against its respective host.

## Local config files (PII — gitignored)

Team identities are **not** committed (phishing/PII concern). The project is
configured by two files:

- **`omni-project.toml`** — committed, PII-free project config (Jira/GitHub/
  GitLab targets, mirror remotes, sync flags, label map). Validated against
  [schema/omni-project.schema.json](schema/omni-project.schema.json) via a
  top-level `schema_version` for forward evolution.
- **`users.toml`** — gitignored team roster (emails -> per-host usernames and
  group membership). The GitHub-login -> Jira-email developer map is derived
  from it. Groups provide metadata for future GitHub team provisioning and
  CODEOWNERS generation.

Copy the templates and fill in real values (or run `omni-sync init`):

```sh
cp users.toml.example users.toml       # [users."<email>"] roster
cp .env.example       .env             # tokens (JIRA_API_TOKEN, GITLAB_TOKEN)
```

The CLI searches upward from the current directory for `omni-project.toml` /
`users.toml` / `.env` and warns (pointing at `omni-sync init`) if the
local-only ones are missing, so it works when invoked from any directory in or
above the checkout.

## Identity roster (cross-host assignees)

`--assignee` on `create` and `pr` accepts either a provider username or an
**email address**. Emails are the pivot field: the same person resolves to the
right username on each host via `users.toml` (gitignored; see
[users.toml.example](users.toml.example)), one table per person keyed on email:

```toml
[users."person.one@agency.gov"]
gh     = "gh-login-1"        # github.com (GSA-TTS)
helix  = "ghes-login-1"      # github.helix.gsa.gov — the login, NOT the _gsagov SSO form
gitlab = "gitlab-login-1"    # workshop.cloud.gov

[groups."example-team"]
github_org = "example-org"
github_team = "example-team"
members = ["person.one@agency.gov"]
```

So `--assignee person.one@agency.gov --to gh-helix` assigns `ghes-login-1`,
while the same flag `--to gl-cg` assigns `gitlab-login-1`. A plain username
passes through unchanged; an email with no mapping for that host is skipped
with a warning rather than failing the whole command.

Group members must reference email keys declared under `[users]`. Host fields
may be omitted or set to an empty string while a username is not yet known.

> Note the Helix value is the login, not the `_gsagov` SSO handle — see the
> Helix SSO note under Authentication.

## Usage

Create the same issue across multiple targets:

```sh
uv run omni-sync create "Migrate core auth service" "Update the OIDC endpoints." --to gh-tts --to gh-helix --to jira-mod
```

Batch commands continue processing independent targets or tickets after an
item fails, but return exit code `1` if any item failed. An exit code of `0`
therefore means the entire requested batch succeeded.

Render open issues authored by or assigned to the authenticated user across
GitHub.com, GitHub Helix, GitLab, and Jira:

```sh
uv run omni-sync board
uv run omni-sync board --output open-issues.md --body-limit 240
```

The report contains one Mermaid Kanban board per provider so each board can use
its own configured issue URL template. Set optional `[board]` values `gh_tts_url`,
`gh_helix_url`, `gl_cg_url`, and `jira_mod_url`; omitted values are derived from
the configured host and resource. Templates use `#TICKET#` for the issue ID.
Direct links are also included in the details
table below each board. Repository/project values and host overrides come from
the selected project context (`omni-project.toml` plus its sibling `.env`).
Independent provider failures are rendered in the report and produce exit code
`1` after the remaining providers have been queried.

Diff an issue between two systems:

```sh
uv run omni-sync diff gh-helix 4 gl-cg 88
```

Preview reconciliation (dry run, default):

```sh
uv run omni-sync sync gh-helix 4 gl-cg 88 --direction left-to-right
```

Apply the reconciliation:

```sh
uv run omni-sync sync gh-helix 4 gl-cg 88 --direction left-to-right --apply
```

## Config-driven GitHub ↔ Jira sync (GSA FedRAMP `acli` workflow)

A second, battle-tested sync flow (transposed from the GSA-TTS petrified-forest
tooling) drives GitHub ↔ GSA GovCloud Jira (project `FPDF`) via the Atlassian
CLI (`acli`), configured entirely through [omni-project.toml](omni-project.toml).

Two deliberately separate one-directional flows avoid split-brain oscillation:

```sh
# Jira <- GitHub: labels, assignee, milestone-as-label, idempotent sync comment
uv run omni-sync gh-jira sync-jira-from-github --dry-run
uv run omni-sync gh-jira sync-jira-from-github --jira-key FPDF-395 --apply

# GitHub <- Jira: backfill GitHub assignee from Jira (assignee only, fail-closed)
uv run omni-sync gh-jira backfill-github-from-jira --dry-run
uv run omni-sync gh-jira backfill-github-from-jira --limit 10 --apply
```

Key safety invariants carried over from the source tooling:

- **Never writes the Jira `description` field.** A 2026-09-21 incident flattened
  rich ADF formatting on ~82 real tickets by round-tripping descriptions through
  plain text. Sync state now lives in a single dedicated **comment**, found by a
  leading `[github-sync]` marker line and updated in place.
- **`acli` has no Sprint/Fix Version flag**, so GitHub milestones are encoded as
  prefixed Jira labels (`milestone:PI-6-Iteration-6.1`). Only *managed* milestone
  labels are ever removed — human-set labels are never touched.
- **Backfill is fail-closed**: it only sets a GitHub assignee when GitHub has
  none, the Jira ticket is non-Done and assigned, and the Jira assignee maps to a
  known GitHub login (derived from `users.toml`). Every other case is reported, not guessed.
- Reads GitHub via REST (`gh api --paginate`), leaving the GraphQL project quota
  untouched.

## Architecture

```
harness/
├── cli.py                     # Entry point: create, board, sync, diff, gh-jira, mirror, doctor, preflight, bench, init
├── config.py                  # omni-project.toml loader + schema validation + label/assignee mapping
├── workspace.py               # Discover omni-project.toml upward from CWD
├── identity.py                # users.toml roster (email-pivoted cross-host lookups)
├── models.py                  # CanonicalIssue, FieldDelta, DiffResult, sync anchor helpers
├── transformers/
│   ├── markdown_jira.py       # GFM <-> Atlassian Document Format
│   └── sanitizers.py          # Strip anchor/HTML comment helpers
├── adapters/
│   ├── base.py                # Abstract adapter + subprocess CLI runner
│   ├── github.py              # Wraps `gh` (github.com and GHES via GH_HOST)
│   ├── github_rest.py         # REST issue enumeration + key-in-title grouping
│   ├── gitlab.py              # Wraps `glab` (GITLAB_HOST)
│   ├── jira.py                # Wraps `jira-cli`
│   └── acli_jira.py           # Wraps `acli jira workitem` (GSA GovCloud; comment-based sync)
└── engine/
    ├── diff.py                # Field-level structural diff
    ├── reconciler.py          # One-directional patch application
    └── gh_jira_sync.py        # Config-driven GitHub<->Jira sync flows
```

### Sync anchors

Cross-system identity is tracked via an HTML-comment footer injected into
each issue body:

```markdown
<!-- fed-sync-anchor: urn:fed:sync:a1b2c3d4 -->
<!-- links: gh-tts:12 | gh-helix:4 | gl-cg:88 | jira:PROJECT-402 -->
```

The diff engine strips this footer before comparing bodies so link metadata
never produces a false-positive delta.

## Verifying setup

`doctor` is a read-only check that confirms the provider CLIs are installed
and authenticated, the config parses, and the Jira token is present. It
auto-loads `.env`, so `GITLAB_TOKEN` / `JIRA_API_TOKEN` set there are picked up:

```sh
uv run omni-sync doctor
```

## Secret scanning

A [betterleaks](https://github.com/betterleaks/betterleaks) config
([betterleaks.toml](betterleaks.toml)) scans the repo for API keys and tokens.
It keeps the full default rule set and allowlists only the gitignored local
secret files (`.env`, `.env.*`, SSH config backups); `.env.example` is still
scanned since it holds placeholders only.

```sh
betterleaks dir . --config betterleaks.toml
```

## Testing

```sh
uv run pytest
```

All adapter tests mock `subprocess.run`; no live network calls are made
against GitHub, GitLab, or Jira in the standard test suite.

## Releases

CI builds a standalone [PyApp](https://ofek.dev/pyapp/) binary (Linux, macOS
arm64, Windows) for omni-sync via `uv`:

- **Every merge to `main`** publishes an auto patch release `1.0.<run-number>`.
- **Pushing a `v1.1.0`-style tag** cuts that exact version (minor/major bump).

Release notes and `CHANGELOG.md` are generated from Conventional Commits by
[git-cliff](https://git-cliff.org) (`cliff.toml`), run through `mise`. Use
Conventional Commit prefixes (`feat:`, `fix:`, `docs:`, `ci:`, …) so changes
are grouped correctly. Workflows: [.github/workflows/ci.yml](.github/workflows/ci.yml)
(tests + schema validation on every PR) and
[.github/workflows/release.yml](.github/workflows/release.yml).

To cut a minor/major release:

```sh
git tag v1.1.0 && git push origin v1.1.0   # release.yml builds + publishes
```
