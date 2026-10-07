"""Unified CLI entry point: create, sync, and diff issues across GitHub.com,
GitHub Enterprise Server, GitLab, and Jira without needing provider-specific
tooling knowledge.
"""
from __future__ import annotations

import os
from pathlib import Path

import typer

from harness.adapters.acli_jira import AcliJiraAdapter
from harness.adapters.base import AdapterError, BaseIssueAdapter
from harness.adapters.github import GitHubAdapter
from harness.adapters.github_rest import GitHubRestAdapter
from harness.adapters.gitlab import GitLabAdapter
from harness.adapters.jira import JiraAdapter
from harness.config import load_config
from harness.engine.gh_jira_sync import (
    build_jira_index,
    plan_backfill_github_from_jira,
    sync_jira_from_github,
)
from harness.engine.board import collect_boards, render_boards
from harness.engine.mirror import GitMirror
from harness.engine.preflight import check_github, check_gitlab, check_jira
from harness.engine.reconciler import reconcile
from harness.identity import UserRoster
from harness.models import CanonicalIssue, IssueQuery
from harness.resources import resource_text
from harness.workspace import (
    LOCAL_ONLY,
    config_path,
    find_workspace,
    missing_local_files,
    template_name,
)

app = typer.Typer(help="Unified issue CLI across GitHub, GitHub Enterprise, GitLab, and Jira.")


def _warn_missing_local(workspace: Path | None = None) -> None:
    """Warn once if local-only config files are absent, pointing at `init`."""
    missing = missing_local_files(workspace)
    if missing:
        ws = workspace or find_workspace()
        typer.echo(
            f"warning: missing in {ws}: {', '.join(missing)} — run `omni-sync init` to create from templates",
            err=True,
        )


def _runtime_config(config: Path | None = None) -> Path:
    """Resolve a config at command execution, never at module import time."""
    return config.resolve() if config is not None else config_path("omni-project.toml")


def _resolve_assignees(target: str, values: list[str], workspace: Path | None = None) -> list[str]:
    """Translate assignee emails to the target host's usernames via users.toml.

    A value that is already a username passes through. An email with a mapping
    becomes that host's username; an email with no mapping is dropped with a
    warning so a create/PR doesn't fail on an unknown person.
    """
    if not values:
        return []
    roster = UserRoster.load(config_path("users.toml", workspace))
    resolved: list[str] = []
    for value in values:
        username = roster.resolve_assignee(target, value)
        if username is None:
            typer.echo(f"  (skipping assignee '{value}': no mapping for {target} in users.toml)", err=True)
            continue
        resolved.append(username)
    return resolved


def _email_to_login_map(cfg: dict, workspace: Path | None = None) -> dict[str, str]:
    """Jira email -> GitHub login, derived from the users.toml roster.

    Prefers github.com logins, falling back to Helix. Used by the
    Jira -> GitHub assignee backfill.
    """
    roster = UserRoster.load(config_path("users.toml", workspace))
    out: dict[str, str] = {}
    for login, email in roster.github_login_to_jira_email().items():
        out.setdefault(email.lower(), login)
    return out


def _load_dotenv(path: Path | None = None) -> None:
    """Load KEY=VALUE lines from .env into os.environ without overriding existing values.

    Lets `glab`/`acli` pick up GITLAB_TOKEN/JIRA_API_TOKEN from the gitignored
    .env the same way the shell would, without a third-party dependency.
    """
    env_path = path or config_path(".env")
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


# Target registry: lazily constructed so missing env vars only error if the
# target is actually used.
_TARGET_FACTORIES: dict[str, type] = {}


def _github_com(repo: str) -> GitHubAdapter:
    return GitHubAdapter(os.environ.get("GITHUB_PUBLIC_HOST", "github.com"), repo)


def _github_helix(repo: str) -> GitHubAdapter:
    return GitHubAdapter(os.environ.get("HELIX_GH_HOST", "github.helix.gsa.gov"), repo)


def _gitlab_cloudgov(repo: str) -> GitLabAdapter:
    return GitLabAdapter(os.environ.get("CLOUDGOV_GLAB_HOST", "workshop.cloud.gov"), repo)


def _jira_mod(project: str) -> JiraAdapter:
    return JiraAdapter(
        os.environ.get("JIRA_INSTANCE_URL", "https://gsa-standard.atlassian-us-gov-mod.net"),
        project,
    )


_ADAPTER_BUILDERS = {
    "gh-tts": _github_com,
    "gh-helix": _github_helix,
    "gl-cg": _gitlab_cloudgov,
    "jira-mod": _jira_mod,
}

# target -> repo/project identifier. In real usage these come from a config
# file; kept as env-driven overrides here to stay dependency-free.
_TARGET_RESOURCE_ENV = {
    "gh-tts": "GH_TTS_REPO",
    "gh-helix": "GH_HELIX_REPO",
    "gl-cg": "GL_CG_REPO",
    "jira-mod": "JIRA_MOD_PROJECT",
}


def _resolve_adapter(target: str) -> BaseIssueAdapter:
    _load_dotenv()
    if target not in _ADAPTER_BUILDERS:
        raise typer.BadParameter(f"Unknown target '{target}'. Valid: {', '.join(_ADAPTER_BUILDERS)}")
    resource_env = _TARGET_RESOURCE_ENV[target]
    resource = os.environ.get(resource_env)
    if not resource:
        raise typer.BadParameter(f"Set {resource_env} to the repo/project for target '{target}'")
    return _ADAPTER_BUILDERS[target](resource)


@app.command()
def create(
    title: str,
    body: str,
    to: list[str] = typer.Option(..., "--to", help="Target systems: gh-tts, gh-helix, gl-cg, jira-mod"),
    assignee: list[str] = typer.Option(None, "--assignee", help="Email (mapped per host via users.toml) or username; repeatable"),
) -> None:
    """Create the same issue across one or more target systems."""
    results: dict[str, str] = {}
    any_fail = False

    for target in to:
        adapter = _resolve_adapter(target)
        canonical = CanonicalIssue.create_new(title=title, body_markdown=body)
        canonical.assignees = _resolve_assignees(target, assignee or [])
        try:
            remote_id = adapter.create_issue(canonical)
        except AdapterError as exc:
            typer.echo(f"FAILED on {target}: {exc}", err=True)
            any_fail = True
            continue
        results[target] = remote_id
        typer.echo(f"Created on {target}: {remote_id}")

    if any_fail or not results:
        raise typer.Exit(code=1)


@app.command()
def board(
    config: Path | None = typer.Option(None, "--config", help="Path to omni-project.toml"),
    output: Path = typer.Option(Path("open-issues.md"), "--output", help="Consolidated Markdown report path"),
    relationship: list[str] = typer.Option(None, "--relationship", help="authored or assigned; repeatable (default: both)"),
    user: list[str] = typer.Option(None, "--user", help="@me, roster email, or provider username; repeatable"),
    state: str = typer.Option("open", "--state", help="open, closed, or all"),
    label: list[str] = typer.Option(None, "--label", help="Require label; repeatable (AND semantics)"),
    search: str | None = typer.Option(None, "--search", help="Search issue title and body"),
    target: list[str] = typer.Option(None, "--target", help="Provider target; repeatable (default: all four)"),
    limit: int = typer.Option(100, "--limit", help="Maximum issues per authored/assigned query"),
    body_limit: int = typer.Option(180, "--body-limit", help="Maximum body characters per card"),
) -> None:
    """Write one agent- and human-readable Markdown issue report."""
    if limit < 1:
        raise typer.BadParameter("limit must be at least 1")
    if limit > 100:
        raise typer.BadParameter("limit cannot exceed 100")
    if body_limit < 1:
        raise typer.BadParameter("body-limit must be at least 1")
    relationships = tuple(relationship or ("authored", "assigned"))
    users = tuple(user or ("@me",))
    labels = tuple(label or ())
    selected_targets = tuple(target or ("gh-tts", "gh-helix", "gl-cg", "jira-mod"))
    invalid_relationships = sorted(set(relationships) - {"authored", "assigned"})
    invalid_targets = sorted(set(selected_targets) - set(_TARGET_RESOURCE_ENV))
    if invalid_relationships:
        raise typer.BadParameter(f"invalid relationship: {', '.join(invalid_relationships)}")
    if state not in {"open", "closed", "all"}:
        raise typer.BadParameter("state must be open, closed, or all")
    if invalid_targets:
        raise typer.BadParameter(f"invalid target: {', '.join(invalid_targets)}")

    config = _runtime_config(config)
    _load_dotenv(config.parent / ".env")
    cfg = load_config(config)
    roster = UserRoster.load(config.parent / "users.toml") if any("@" in value and value != "@me" for value in users) else UserRoster({})
    query = IssueQuery(relationships, users, state, labels, search, limit)
    boards, errors = collect_boards(cfg, roster, query, selected_targets)
    for error in errors:
        typer.echo(error, err=True)

    filters = {
        "Relationships": ", ".join(relationships),
        "Users": ", ".join(users),
        "State": state,
        "Labels": ", ".join(labels) or "any",
        "Search": search or "none",
        "Targets": ", ".join(selected_targets),
    }
    markdown = render_boards(boards, body_limit, filters)
    try:
        output.write_text(markdown, encoding="utf-8")
    except OSError as exc:
        typer.echo(f"FAILED writing {output}: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"wrote {output}")
    if errors:
        raise typer.Exit(code=1)


@app.command()
def diff(
    source: str,
    source_id: str,
    target: str,
    target_id: str,
) -> None:
    """Diff an issue between two systems and print a unified table."""
    left_adapter = _resolve_adapter(source)
    right_adapter = _resolve_adapter(target)
    try:
        left = left_adapter.get_issue(source_id)
        right = right_adapter.get_issue(target_id)
    except AdapterError as exc:
        typer.echo(f"FAILED: {exc}", err=True)
        raise typer.Exit(code=1)

    typer.echo(left.diff(right).render_table())


@app.command()
def sync(
    source: str,
    source_id: str,
    target: str,
    target_id: str,
    direction: str = typer.Option(
        "left-to-right", "--direction", help="left-to-right or right-to-left"
    ),
    body_mode: str = typer.Option(
        "replace", "--body-mode", help="How to write the body: replace, append, or comment"
    ),
    dry_run: bool = typer.Option(True, "--dry-run/--apply", help="Preview only (default) or apply changes"),
) -> None:
    """Reconcile drift between two issues, applying changes in one direction."""
    if direction not in ("left-to-right", "right-to-left"):
        raise typer.BadParameter("direction must be left-to-right or right-to-left")
    if body_mode not in ("replace", "append", "comment"):
        raise typer.BadParameter("body-mode must be replace, append, or comment")

    left_adapter = _resolve_adapter(source)
    right_adapter = _resolve_adapter(target)
    try:
        result = reconcile(
            left_adapter,
            source_id,
            right_adapter,
            target_id,
            direction=direction,
            dry_run=dry_run,
            body_mode=body_mode,
        )
    except AdapterError as exc:
        typer.echo(f"FAILED: {exc}", err=True)
        raise typer.Exit(code=1)

    typer.echo(result.diff.render_table())
    if dry_run:
        typer.echo(f"\n(dry run - body-mode={body_mode}; use --apply to write changes)")
    elif result.applied:
        typer.echo(f"\nApplied changes direction={direction} body-mode={body_mode}")
    else:
        typer.echo("\nNo changes to apply.")


gh_jira = typer.Typer(help="Config-driven GitHub<->Jira sync (GSA FedRAMP acli workflow).")
app.add_typer(gh_jira, name="gh-jira")

@gh_jira.command("sync-jira-from-github")
def sync_jira_from_github_cmd(
    config: Path | None = typer.Option(None, "--config", help="Path to omni-project.toml"),
    jira_key: str = typer.Option(None, "--jira-key", help="Only sync this key, e.g. FPDF-395"),
    repo: list[str] = typer.Option(None, "--repo", help="Limit to repo(s); defaults to config"),
    limit: int = typer.Option(0, "--limit", help="Cap processed tickets"),
    dry_run: bool = typer.Option(True, "--dry-run/--apply", help="Preview (default) or write"),
) -> None:
    """Jira <- GitHub: labels, assignee, milestone-as-label, and sync comment.

    Never writes the Jira description field. GitHub is authoritative for
    engineering execution state.
    """
    config = _runtime_config(config)
    _load_dotenv(config.parent / ".env")
    cfg = load_config(config)
    gh = GitHubRestAdapter(cfg["github"]["org"], cfg["jira"].get("project_key", "FPDF"))
    jira = AcliJiraAdapter(cfg["jira"].get("acli_bin", "acli"), cfg["jira"]["project_key"])
    repos = repo or cfg["github"]["repos"]

    grouped: dict[str, list[dict]] = {}
    for r in repos:
        try:
            items = gh.paginate_issues(r)
        except AdapterError as exc:
            typer.echo(f"FAILED on {r}: {exc}", err=True)
            raise typer.Exit(code=1)
        for key, bucket in gh.group_by_key(items).items():
            grouped.setdefault(key, []).extend(bucket)

    keys = sorted(grouped)
    if jira_key:
        keys = [k for k in keys if k.upper() == jira_key.upper()]
    if limit:
        keys = keys[:limit]

    any_fail = False
    for key in keys:
        try:
            result = sync_jira_from_github(grouped[key], jira, key, cfg, dry_run=dry_run)
        except AdapterError as exc:
            typer.echo(f"{key}: ERROR: {exc}", err=True)
            any_fail = True
            continue
        actions = "; ".join(result["actions"]) or "-"
        typer.echo(f"{key} (#{result['gh_number']}, {result['linked_count']} linked): {actions}")
        for err in result["errors"]:
            typer.echo(f"  ERROR: {err}", err=True)
            any_fail = True

    if dry_run:
        typer.echo("\n(dry run - no changes written; use --apply to sync)")
    if any_fail:
        raise typer.Exit(code=1)


@gh_jira.command("backfill-github-from-jira")
def backfill_github_from_jira_cmd(
    config: Path | None = typer.Option(None, "--config", help="Path to omni-project.toml"),
    jira_key: str = typer.Option(None, "--jira-key", help="Only process this key, e.g. FPDF-463"),
    repo: list[str] = typer.Option(None, "--repo", help="Limit to repo(s); defaults to config"),
    limit: int = typer.Option(0, "--limit", help="Cap processed items"),
    dry_run: bool = typer.Option(True, "--dry-run/--apply", help="Preview (default) or write"),
) -> None:
    """GitHub <- Jira: backfill GitHub assignee from Jira (assignee only, fail-closed).

    Only acts when GitHub has no assignee, the Jira ticket is non-Done and
    assigned, and the Jira assignee maps to a known GitHub login.
    """
    config = _runtime_config(config)
    _load_dotenv(config.parent / ".env")
    cfg = load_config(config)
    gh = GitHubRestAdapter(cfg["github"]["org"], cfg["jira"].get("project_key", "FPDF"))
    jira = AcliJiraAdapter(cfg["jira"].get("acli_bin", "acli"), cfg["jira"]["project_key"])
    repos = repo or cfg["github"]["repos"]

    try:
        jira_issues = jira._run_cli(
            [
                jira.acli_bin, "jira", "workitem", "search",
                "--jql", f"project = {cfg['jira']['project_key']}",
                "--limit", "600", "--json",
            ]
        )
    except AdapterError as exc:
        typer.echo(f"FAILED: {exc}", err=True)
        raise typer.Exit(code=1)
    jira_index = build_jira_index(jira_issues if isinstance(jira_issues, list) else [])
    email_to_login = _email_to_login_map(cfg, config.parent)

    plans: list[dict] = []
    for r in repos:
        try:
            items = gh.paginate_issues(r, state="open")
        except AdapterError as exc:
            typer.echo(f"FAILED on {r}: {exc}", err=True)
            raise typer.Exit(code=1)
        for item in items:
            key = gh.key_in_title(item.get("title", ""))
            if not key or (jira_key and key.upper() != jira_key.upper()):
                continue
            plan = plan_backfill_github_from_jira(item, key, jira_index, email_to_login)
            plan["repo"] = r
            plans.append(plan)

    if limit:
        plans = plans[:limit]

    any_fail = False
    for plan in plans:
        if plan["action"] == "backfill":
            ok, msg = gh.add_assignee(plan["repo"], plan["gh_number"], plan["login"], dry_run=dry_run)
            status = msg if ok else f"ERROR: {msg}"
            any_fail = any_fail or not ok
        else:
            status = f"skip ({plan['reason']})"
        typer.echo(f"{plan['key']} #{plan['gh_number']}: {status}")

    if dry_run:
        typer.echo("\n(dry run - no changes written; use --apply to backfill)")
    if any_fail:
        raise typer.Exit(code=1)


@app.command()
def doctor(
    config: Path | None = typer.Option(None, "--config", help="Path to omni-project.toml"),
) -> None:
    """Verify provider CLI auth and config without mutating anything.

    Checks that gh/glab/acli are installed and authenticated for the hosts
    this project targets, that omni-project.toml parses, and that the Jira
    API token is present. Read-only.
    """
    import shutil
    import subprocess

    ok = True

    config = _runtime_config(config)
    _load_dotenv(config.parent / ".env")

    def check(label: str, passed: bool, detail: str = "") -> None:
        nonlocal ok
        mark = "OK  " if passed else "FAIL"
        ok = ok and passed
        typer.echo(f"[{mark}] {label}" + (f" — {detail}" if detail else ""))

    def cli_present(name: str) -> bool:
        return shutil.which(name) is not None

    def run_quiet(argv: list[str]) -> tuple[int, str]:
        try:
            r = subprocess.run(argv, capture_output=True, text=True, timeout=30)
            return r.returncode, (r.stdout + r.stderr).strip()
        except (OSError, subprocess.TimeoutExpired) as exc:
            return 1, str(exc)

    def run_quiet_env(argv: list[str], extra_env: dict[str, str]) -> tuple[int, str]:
        try:
            r = subprocess.run(
                argv, capture_output=True, text=True, timeout=30, env={**os.environ, **extra_env}
            )
            return r.returncode, (r.stdout + r.stderr).strip()
        except (OSError, subprocess.TimeoutExpired) as exc:
            return 1, str(exc)

    typer.echo("omni-sync doctor\n")

    # --- CLIs installed ---
    gh_ok = cli_present("gh")
    glab_ok = cli_present("glab")
    acli_ok = cli_present("acli")
    check("gh installed", gh_ok)
    check("glab installed", glab_ok)
    check("acli installed", acli_ok)

    # --- gh auth (github.com + Helix) ---
    if gh_ok:
        public_host = os.environ.get("GITHUB_PUBLIC_HOST", "github.com")
        helix_host = os.environ.get("HELIX_GH_HOST", "github.helix.gsa.gov")
        rc, _ = run_quiet(["gh", "auth", "status", "--hostname", public_host])
        check(f"gh authenticated ({public_host})", rc == 0)
        rc, _ = run_quiet(["gh", "auth", "status", "--hostname", helix_host])
        check(f"gh authenticated ({helix_host})", rc == 0, "" if rc == 0 else "run: gh auth login --hostname " + helix_host)

    # --- glab auth ---
    if glab_ok:
        glab_host = os.environ.get("CLOUDGOV_GLAB_HOST", "workshop.cloud.gov")
        rc, _ = run_quiet(["glab", "auth", "status", "--hostname", glab_host])
        if rc != 0 and os.environ.get("GITLAB_TOKEN"):
            # glab auth status ignores GITLAB_TOKEN; confirm the env token works via an API call.
            rc, _ = run_quiet_env(["glab", "api", "user"], {"GITLAB_HOST": glab_host})
            detail = "via GITLAB_TOKEN" if rc == 0 else "GITLAB_TOKEN set but API call failed"
            check(f"glab authenticated ({glab_host})", rc == 0, detail)
        else:
            check(f"glab authenticated ({glab_host})", rc == 0, "" if rc == 0 else "run: glab auth login --hostname " + glab_host)

    # --- acli auth ---
    if acli_ok:
        rc, out = run_quiet(["acli", "jira", "auth", "status"])
        check("acli authenticated", rc == 0 and "Authenticated" in out)

    # --- betterleaks (secret scanning) ---
    bl_ok = cli_present("betterleaks")
    check("betterleaks installed", bl_ok, "" if bl_ok else "secret scanning unavailable; see mise.toml")

    # --- workspace + config ---
    ws = config.parent
    check(f"workspace found ({ws})", config.exists(), "" if config.exists() else "no omni-project.toml above CWD")
    for name in missing_local_files(ws):
        check(f"local file present ({name})", False, "run: omni-sync init")

    try:
        cfg = load_config(config)
        check(f"config parses + validates ({config.name})", True)
        repos = cfg.get("github", {}).get("repos", [])
        check("config: github.repos non-empty", bool(repos), f"{len(repos)} repo(s)")
        check("config: jira.project_key set", bool(cfg.get("jira", {}).get("project_key")))
    except SystemExit as exc:
        check(f"config parses + validates ({config.name})", False, str(exc))

    # --- Jira token present (never printed) ---
    check("JIRA_API_TOKEN in env", bool(os.environ.get("JIRA_API_TOKEN")), "set in .env (gitignored)" if os.environ.get("JIRA_API_TOKEN") else "copy .env.example to .env")

    typer.echo("")
    if ok:
        typer.echo("All checks passed.")
    else:
        typer.echo("Some checks failed — see above.")
        raise typer.Exit(code=1)


@app.command("pr")
def pr(
    title: str,
    base: str = typer.Option(..., "--base", help="Base/target branch to merge into"),
    head: str = typer.Option(..., "--head", help="Source branch containing the changes"),
    body: str = typer.Option("", "--body", help="PR/MR description"),
    to: list[str] = typer.Option(..., "--to", help="Targets: gh-tts, gh-helix, gl-cg"),
    draft: bool = typer.Option(False, "--draft", help="Open as a draft"),
    assignee: list[str] = typer.Option(None, "--assignee", help="Email (mapped per host via users.toml) or username; repeatable"),
) -> None:
    """Open the same pull/merge request across one or more GitHub/GitLab targets."""
    results: dict[str, str] = {}
    any_fail = False
    for target in to:
        adapter = _resolve_adapter(target)
        assignees = _resolve_assignees(target, assignee or [])
        try:
            url = adapter.create_pull_request(
                title, body, base=base, head=head, draft=draft, assignees=assignees
            )
        except AdapterError as exc:
            typer.echo(f"FAILED on {target}: {exc}", err=True)
            any_fail = True
            continue
        results[target] = url
        typer.echo(f"Opened on {target}: {url}")
    if any_fail or not results:
        raise typer.Exit(code=1)


@app.command()
def preflight(
    config: Path | None = typer.Option(None, "--config", help="Path to omni-project.toml"),
) -> None:
    """Check that each configured target exists and is writable (read-only).

    Verifies repo/project visibility, issues enabled, and write access per
    target so a create/sync fails fast with a clear message instead of a raw
    CLI error mid-run. Targets resolve from env vars (as `omni-sync create`).
    """
    config = _runtime_config(config)
    _load_dotenv(config.parent / ".env")
    cfg = load_config(config)
    results = []

    helix = os.environ.get("GH_HELIX_REPO")
    if helix:
        results.append(check_github(os.environ.get("HELIX_GH_HOST", "github.helix.gsa.gov"), helix))
    tts = os.environ.get("GH_TTS_REPO")
    if tts:
        results.append(check_github(os.environ.get("GITHUB_PUBLIC_HOST", "github.com"), tts))
    glcg = os.environ.get("GL_CG_REPO")
    if glcg:
        results.append(check_gitlab(os.environ.get("CLOUDGOV_GLAB_HOST", "workshop.cloud.gov"), glcg))
    jira_project = os.environ.get("JIRA_MOD_PROJECT") or cfg.get("jira", {}).get("project_key")
    if jira_project:
        results.append(check_jira(cfg.get("jira", {}).get("acli_bin", "acli"), jira_project))

    if not results:
        typer.echo("No targets configured (set GH_HELIX_REPO / GH_TTS_REPO / GL_CG_REPO / JIRA_MOD_PROJECT)", err=True)
        raise typer.Exit(code=1)

    any_fail = False
    for r in results:
        mark = "OK  " if r.ok else "FAIL"
        any_fail = any_fail or not r.ok
        typer.echo(f"[{mark}] {r.target} {r.resource}: {r.detail}")

    if any_fail:
        raise typer.Exit(code=1)


@app.command()
def mirror(
    ref: str = typer.Option("main", "--ref", help="Git ref/branch to push"),
    to: list[str] = typer.Option(None, "--to", help="Mirror targets from [mirror] config; defaults to all"),
    config: Path | None = typer.Option(None, "--config", help="Path to omni-project.toml"),
    dry_run: bool = typer.Option(True, "--dry-run/--apply", help="Preview (default) or push"),
    batch: bool = typer.Option(False, "--batch", help="Non-interactive: fail fast instead of prompting for SSH passphrase"),
) -> None:
    """Push the current repo's code to one or more mirror remotes.

    Auth works the same whether a remote is HTTPS (gh web session / credential
    helper) or SSH (agent/keychain) -- the command does not depend on either.
    Remotes are read from the [mirror] table of omni-project.toml. One
    unreachable remote is reported but does not abort the others.
    """
    config = _runtime_config(config)
    cfg = load_config(config)
    remotes = cfg.get("mirror", {})
    if not remotes:
        typer.echo("No [mirror] remotes configured in omni-project.toml", err=True)
        raise typer.Exit(code=1)

    targets = to or sorted(remotes)
    results = GitMirror(remotes, batch=batch).push(ref, targets, dry_run=dry_run)

    any_fail = False
    for r in results:
        mark = "OK  " if r.ok else "FAIL"
        any_fail = any_fail or not r.ok
        typer.echo(f"[{mark}] {r.remote} ({r.url or '—'}): {r.message}")

    if dry_run:
        typer.echo("\n(dry run - nothing pushed; use --apply to push)")
    elif any_fail:
        raise typer.Exit(code=1)


@app.command()
def bench(
    target: str = typer.Option("jira-mod", "--target", help="Target to benchmark"),
    issue_id: str = typer.Option(..., "--id", help="An existing issue/ticket id to read"),
    runs: int = typer.Option(3, "--runs", help="Repetitions for latency sampling"),
) -> None:
    """Measure CLI invocation count and latency for a read of one issue.

    Attaches a CliMetrics collector to the adapter and performs the full
    `get_issue` path, which for the acli Jira adapter must stay at exactly ONE
    `workitem view` call per key (regression guard — it used to be 4).
    """
    from harness.adapters.base import CliMetrics
    from harness.testing.bench import OpMetric, render_matrix

    config = _runtime_config()
    _load_dotenv(config.parent / ".env")

    def build_adapter():
        # Jira benchmarking uses the acli adapter (the gh-jira flow), not the
        # jira-cli-based JiraAdapter that `_resolve_adapter` returns.
        if target == "jira-mod":
            cfg = load_config(config)
            return AcliJiraAdapter(cfg["jira"].get("acli_bin", "acli"), cfg["jira"]["project_key"])
        return _resolve_adapter(target)

    metrics = CliMetrics()
    # Fresh adapter per run so the per-key view cache does not mask repeat
    # work -- we want to measure a cold get_issue each time.
    for _ in range(max(1, runs)):
        adapter = build_adapter()
        adapter.metrics = metrics
        try:
            adapter.get_issue(issue_id)
        except AdapterError as exc:
            typer.echo(f"FAILED: {exc}", err=True)
            raise typer.Exit(code=1)

    calls_per_run = metrics.count // max(1, runs)
    op = OpMetric(
        provider=target,
        operation="get_issue",
        calls=calls_per_run,
        latencies=[s for _, s in metrics.calls],
    )
    typer.echo(render_matrix([op]))
    typer.echo(f"\nTotal CLI calls: {metrics.count} over {runs} run(s) = {calls_per_run}/run")


@app.command()
def init(
    force: bool = typer.Option(False, "--force", help="Overwrite existing files"),
) -> None:
    """Create the local-only config files (users.toml, .env) from templates.

    Writes into the resolved workspace (searched upward from the CWD). Skips
    files that already exist unless --force. The created files are gitignored
    and must be filled in with real values.
    """
    ws = find_workspace()
    created, skipped = [], []
    for name in LOCAL_ONLY:
        dest = ws / name
        if dest.exists() and not force:
            skipped.append(name)
            continue
        dest.write_text(resource_text(template_name(name)), encoding="utf-8")
        created.append(name)

    for name in created:
        typer.echo(f"created {ws / name}")
    for name in skipped:
        typer.echo(f"skipped {name} (exists; use --force to overwrite)")
    if created:
        typer.echo("\nFill in the created files with real values. They are gitignored.")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
