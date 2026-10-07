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
from harness.config import email_to_login_map, load_config
from harness.engine.gh_jira_sync import (
    build_jira_index,
    plan_backfill_github_from_jira,
    sync_jira_from_github,
)
from harness.engine.reconciler import reconcile
from harness.models import CanonicalIssue

app = typer.Typer(help="Unified issue CLI across GitHub, GitHub Enterprise, GitLab, and Jira.")

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
) -> None:
    """Create the same issue across one or more target systems."""
    canonical = CanonicalIssue.create_new(title=title, body_markdown=body)
    results: dict[str, str] = {}

    for target in to:
        adapter = _resolve_adapter(target)
        try:
            remote_id = adapter.create_issue(canonical)
        except AdapterError as exc:
            typer.echo(f"FAILED on {target}: {exc}", err=True)
            continue
        canonical.sync_metadata[target] = remote_id
        results[target] = remote_id
        typer.echo(f"Created on {target}: {remote_id}")

    if not results:
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
    dry_run: bool = typer.Option(True, "--dry-run/--apply", help="Preview only (default) or apply changes"),
) -> None:
    """Reconcile drift between two issues, applying changes in one direction."""
    if direction not in ("left-to-right", "right-to-left"):
        raise typer.BadParameter("direction must be left-to-right or right-to-left")

    left_adapter = _resolve_adapter(source)
    right_adapter = _resolve_adapter(target)
    try:
        result = reconcile(
            left_adapter, source_id, right_adapter, target_id, direction=direction, dry_run=dry_run
        )
    except AdapterError as exc:
        typer.echo(f"FAILED: {exc}", err=True)
        raise typer.Exit(code=1)

    typer.echo(result.diff.render_table())
    if dry_run:
        typer.echo("\n(dry run - no changes applied; use --apply to write changes)")
    elif result.applied:
        typer.echo(f"\nApplied changes direction={direction}")
    else:
        typer.echo("\nNo changes to apply.")


gh_jira = typer.Typer(help="Config-driven GitHub<->Jira sync (GSA FedRAMP acli workflow).")
app.add_typer(gh_jira, name="gh-jira")

_DEFAULT_CONFIG = Path(__file__).resolve().parent.parent / "sync_config.toml"


@gh_jira.command("sync-jira-from-github")
def sync_jira_from_github_cmd(
    config: Path = typer.Option(_DEFAULT_CONFIG, "--config", help="Path to sync_config.toml"),
    jira_key: str = typer.Option(None, "--jira-key", help="Only sync this key, e.g. FPDF-395"),
    repo: list[str] = typer.Option(None, "--repo", help="Limit to repo(s); defaults to config"),
    limit: int = typer.Option(0, "--limit", help="Cap processed tickets"),
    dry_run: bool = typer.Option(True, "--dry-run/--apply", help="Preview (default) or write"),
) -> None:
    """Jira <- GitHub: labels, assignee, milestone-as-label, and sync comment.

    Never writes the Jira description field. GitHub is authoritative for
    engineering execution state.
    """
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

    for key in keys:
        result = sync_jira_from_github(grouped[key], jira, key, cfg, dry_run=dry_run)
        actions = "; ".join(result["actions"]) or "-"
        typer.echo(f"{key} (#{result['gh_number']}, {result['linked_count']} linked): {actions}")
        for err in result["errors"]:
            typer.echo(f"  ERROR: {err}", err=True)

    if dry_run:
        typer.echo("\n(dry run - no changes written; use --apply to sync)")


@gh_jira.command("backfill-github-from-jira")
def backfill_github_from_jira_cmd(
    config: Path = typer.Option(_DEFAULT_CONFIG, "--config", help="Path to sync_config.toml"),
    jira_key: str = typer.Option(None, "--jira-key", help="Only process this key, e.g. FPDF-463"),
    repo: list[str] = typer.Option(None, "--repo", help="Limit to repo(s); defaults to config"),
    limit: int = typer.Option(0, "--limit", help="Cap processed items"),
    dry_run: bool = typer.Option(True, "--dry-run/--apply", help="Preview (default) or write"),
) -> None:
    """GitHub <- Jira: backfill GitHub assignee from Jira (assignee only, fail-closed).

    Only acts when GitHub has no assignee, the Jira ticket is non-Done and
    assigned, and the Jira assignee maps to a known GitHub login.
    """
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
    email_to_login = email_to_login_map(cfg)

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

    for plan in plans:
        if plan["action"] == "backfill":
            ok, msg = gh.add_assignee(plan["repo"], plan["gh_number"], plan["login"], dry_run=dry_run)
            status = msg if ok else f"ERROR: {msg}"
        else:
            status = f"skip ({plan['reason']})"
        typer.echo(f"{plan['key']} #{plan['gh_number']}: {status}")

    if dry_run:
        typer.echo("\n(dry run - no changes written; use --apply to backfill)")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
