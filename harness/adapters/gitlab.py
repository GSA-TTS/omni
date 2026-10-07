"""Adapter wrapping the `glab` CLI, targeting GitLab instances such as
workshop.cloud.gov via the GITLAB_HOST env var.
"""
from __future__ import annotations

from harness.adapters.base import AdapterError, BaseIssueAdapter
from harness.models import CanonicalIssue


class GitLabAdapter(BaseIssueAdapter):
    """Issue adapter for self-hosted/cloud.gov GitLab via `glab`."""

    def __init__(self, host: str, repo: str):
        self.host = host
        self.repo = repo

    def _env(self) -> dict[str, str]:
        return {"GITLAB_HOST": self.host}

    def get_issue(self, issue_id: str) -> CanonicalIssue:
        data = self._run_cli(
            ["glab", "issue", "view", issue_id, "-R", self.repo, "-F", "json"],
            env_overrides=self._env(),
        )
        if not isinstance(data, dict):
            raise AdapterError(f"Unexpected glab issue view output for {issue_id}")
        state = str(data.get("state", "opened")).lower()
        return CanonicalIssue(
            title=data["title"],
            body_markdown=data.get("description") or "",
            status="CLOSED" if state in ("closed", "closed_merge") else "OPEN",
            labels=list(data.get("labels", [])),
            assignees=[a["username"] for a in data.get("assignees", [])],
        )

    def create_issue(self, issue: CanonicalIssue) -> str:
        argv = [
            "glab",
            "issue",
            "create",
            "-R",
            self.repo,
            "--title",
            issue.title,
            "--description",
            issue.body_with_anchor(),
        ]
        if issue.labels:
            argv += ["--label", ",".join(issue.labels)]
        for assignee in issue.assignees:
            argv += ["--assignee", assignee]
        url = self._run_cli(argv, env_overrides=self._env(), parse_json=False)
        return str(url).strip()

    def update_issue(self, issue_id: str, issue: CanonicalIssue) -> None:
        argv = [
            "glab",
            "issue",
            "update",
            issue_id,
            "-R",
            self.repo,
            "--title",
            issue.title,
            "--description",
            issue.body_with_anchor(),
        ]
        self._run_cli(argv, env_overrides=self._env(), parse_json=False)

        # State changes use dedicated subcommands; `glab issue update` has no
        # --close/--reopen flags.
        state_cmd = "close" if issue.status == "CLOSED" else "reopen"
        self._run_cli(
            ["glab", "issue", state_cmd, issue_id, "-R", self.repo],
            env_overrides=self._env(),
            parse_json=False,
        )

    def add_comment(self, issue_id: str, body: str) -> None:
        self._run_cli(
            ["glab", "issue", "note", issue_id, "-R", self.repo, "--message", body],
            env_overrides=self._env(),
            parse_json=False,
        )

    def create_pull_request(
        self, title: str, body: str, base: str, head: str, draft: bool = False
    ) -> str:
        argv = [
            "glab", "mr", "create",
            "-R", self.repo,
            "--source-branch", head,
            "--target-branch", base,
            "--title", title,
            "--description", body,
            "--yes",  # skip interactive prompts
        ]
        if draft:
            argv.append("--draft")
        url = self._run_cli(argv, env_overrides=self._env(), parse_json=False)
        return str(url).strip()
