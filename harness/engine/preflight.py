"""Preflight namespace/permission checks: verify a target resource exists and
is writable *before* a create/sync attempt, so operations fail fast with a
clear message instead of a raw CLI error mid-run.

Motivated by workshop.cloud.gov rejecting project creation
(can_create_project=false) only after an API call -- see
skills/omni-sync/known-failures.md.

Pure report objects; the actual CLI calls are injected so this stays testable
offline.
"""

from __future__ import annotations

import subprocess
from collections.abc import Callable
from dataclasses import dataclass


@dataclass
class PreflightCheck:
    target: str
    resource: str
    ok: bool
    detail: str


Runner = Callable[[list[str], dict[str, str]], tuple[int, str]]


def _default_runner(argv: list[str], env: dict[str, str]) -> tuple[int, str]:
    import os

    try:
        r = subprocess.run(
            argv, capture_output=True, text=True, timeout=30, env={**os.environ, **env}
        )
        return r.returncode, (r.stdout + r.stderr).strip()
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 1, str(exc)


def check_github(
    host: str, repo: str, runner: Runner = _default_runner
) -> PreflightCheck:
    """Verify a GitHub repo exists, has issues enabled, and is push-writable."""
    rc, out = runner(
        [
            "gh",
            "api",
            f"repos/{repo}",
            "--jq",
            "[.has_issues, .permissions.push] | @tsv",
        ],
        {"GH_HOST": host},
    )
    if rc != 0:
        return PreflightCheck(host, repo, False, "repo not found or not visible")
    parts = out.split("\t")
    has_issues = parts[0] == "true" if parts else False
    can_push = len(parts) > 1 and parts[1] == "true"
    if not can_push:
        return PreflightCheck(host, repo, False, "no push access to repo")
    if not has_issues:
        return PreflightCheck(host, repo, False, "issues are disabled on repo")
    return PreflightCheck(host, repo, True, "writable, issues enabled")


def check_gitlab(
    host: str, repo: str, runner: Runner = _default_runner
) -> PreflightCheck:
    """Verify a GitLab project exists, has issues enabled, and grants Developer+ access."""
    rc, out = runner(
        ["glab", "api", f"projects/{repo.replace('/', '%2F')}"],
        {"GITLAB_HOST": host},
    )
    if rc != 0:
        if "401" in out or "Unauthorized" in out:
            return PreflightCheck(
                host,
                repo,
                False,
                "GitLab authentication failed; verify the host token is loaded",
            )
        if "404" in out or "Not Found" in out:
            return PreflightCheck(
                host,
                repo,
                False,
                "project not found or token cannot see its namespace",
            )
        return PreflightCheck(host, repo, False, "GitLab API request failed")
    import json

    try:
        data = json.loads(out)
    except json.JSONDecodeError:
        return PreflightCheck(host, repo, False, "unexpected API response")
    if not data.get("issues_enabled", True):
        return PreflightCheck(host, repo, False, "issues are disabled on project")
    permissions = data.get("permissions") or {}
    project_access = permissions.get("project_access") or {}
    group_access = permissions.get("group_access") or {}
    level = max(
        project_access.get("access_level", 0), group_access.get("access_level", 0)
    )
    if level < 30:  # Developer
        return PreflightCheck(
            host,
            repo,
            False,
            "project is visible but write access is unverified; inspect project/group membership",
        )
    return PreflightCheck(host, repo, True, f"writable (access level {level})")


def check_jira(
    acli_bin: str, project_key: str, runner: Runner = _default_runner
) -> PreflightCheck:
    """Verify the Jira project is visible via acli search."""
    rc, _ = runner(
        [
            acli_bin,
            "jira",
            "workitem",
            "search",
            "--jql",
            f"project = {project_key}",
            "--limit",
            "1",
            "--json",
        ],
        {},
    )
    if rc != 0:
        return PreflightCheck(
            "jira", project_key, False, "project not visible or acli not authenticated"
        )
    return PreflightCheck("jira", project_key, True, "project visible")
