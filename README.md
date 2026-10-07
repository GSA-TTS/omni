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

…or, if you already have SSH keys configured, authenticate the API with a token
while keeping SSH for Git operations:

```sh
gh auth login --git-protocol ssh --hostname github.com
gh auth status
```

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

## Usage

Create the same issue across multiple targets:

```sh
uv run omni-sync create "Migrate core auth service" "Update the OIDC endpoints." --to gh-tts --to gh-helix --to jira-mod
```

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
CLI (`acli`), configured entirely through [sync_config.toml](sync_config.toml).

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
  known GitHub login in `[developers]`. Every other case is reported, not guessed.
- Reads GitHub via REST (`gh api --paginate`), leaving the GraphQL project quota
  untouched.

## Architecture

```
harness/
├── cli.py                     # Entry point: create, sync, diff, gh-jira
├── config.py                  # sync_config.toml loader + label/assignee mapping
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

## Testing

```sh
uv run pytest
```

All adapter tests mock `subprocess.run`; no live network calls are made
against GitHub, GitLab, or Jira in the standard test suite.
