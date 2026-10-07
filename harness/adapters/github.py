"""Adapter wrapping the `gh` CLI, supporting both github.com and GitHub
Enterprise Server (e.g. github.helix.gsa.gov) via the GH_HOST env var.
"""
from __future__ import annotations

from harness.adapters.base import AdapterError, BaseIssueAdapter
from harness.models import CanonicalIssue, IssueQuery, OpenIssue

_ISSUE_FIELDS = "title,body,state,labels,assignees,number"


class GitHubAdapter(BaseIssueAdapter):
    """Issue adapter for GitHub.com and GitHub Enterprise Server via `gh`."""

    def __init__(self, host: str, repo: str):
        self.host = host
        self.repo = repo

    def _env(self) -> dict[str, str]:
        return {"GH_HOST": self.host}

    def get_issue(self, issue_id: str) -> CanonicalIssue:
        data = self._run_cli(
            ["gh", "issue", "view", issue_id, "-R", f"{self.host}/{self.repo}", "--json", _ISSUE_FIELDS],
            env_overrides=self._env(),
        )
        if not isinstance(data, dict):
            raise AdapterError(f"Unexpected gh issue view output for {issue_id}")
        return CanonicalIssue(
            title=data["title"],
            body_markdown=data.get("body") or "",
            status="OPEN" if data["state"] == "OPEN" else "CLOSED",
            labels=[label["name"] for label in data.get("labels", [])],
            assignees=[a["login"] for a in data.get("assignees", [])],
        )

    def list_issues(self, query: IssueQuery) -> list[OpenIssue]:
        """List issues matching normalized relationship and content filters."""
        found: dict[int, dict] = {}
        role_flags = {"authored": "--author", "assigned": "--assignee"}
        for relationship in query.relationships:
            for user in query.users:
                argv = [
                    "gh", "issue", "list", "-R", f"{self.host}/{self.repo}",
                    "--state", query.state, role_flags[relationship], user,
                    "--limit", str(query.limit), "--json", "number,title,body,labels,url",
                ]
                for label in query.labels:
                    argv += ["--label", label]
                if query.search:
                    argv += ["--search", query.search]
                data = self._run_cli(argv, env_overrides=self._env())
                if not isinstance(data, list):
                    raise AdapterError(f"Unexpected gh issue list output for {self.repo}")
                for item in data:
                    found[int(item["number"])] = item
        return [
            OpenIssue(
                provider=self.host,
                issue_id=str(number),
                title=item.get("title") or "",
                body=item.get("body") or "",
                labels=tuple(label["name"] for label in item.get("labels", [])),
                url=item.get("url") or f"https://{self.host}/{self.repo}/issues/{number}",
            )
            for number, item in sorted(found.items())
        ]

    def create_issue(self, issue: CanonicalIssue) -> str:
        argv = [
            "gh",
            "issue",
            "create",
            "-R",
            f"{self.host}/{self.repo}",
            "--title",
            issue.title,
            "--body",
            issue.body_with_anchor(),
        ]
        for label in issue.labels:
            argv += ["--label", label]
        for assignee in issue.assignees:
            argv += ["--assignee", assignee]
        url = self._run_cli(argv, env_overrides=self._env(), parse_json=False)
        return str(url).strip()

    def update_issue(self, issue_id: str, issue: CanonicalIssue) -> None:
        argv = [
            "gh",
            "issue",
            "edit",
            issue_id,
            "-R",
            f"{self.host}/{self.repo}",
            "--title",
            issue.title,
            "--body",
            issue.body_with_anchor(),
        ]
        for label in issue.labels:
            argv += ["--add-label", label]
        self._run_cli(argv, env_overrides=self._env(), parse_json=False)

        if issue.status == "CLOSED":
            self._run_cli(
                ["gh", "issue", "close", issue_id, "-R", f"{self.host}/{self.repo}"],
                env_overrides=self._env(),
                parse_json=False,
            )
        else:
            self._run_cli(
                ["gh", "issue", "reopen", issue_id, "-R", f"{self.host}/{self.repo}"],
                env_overrides=self._env(),
                parse_json=False,
            )

    def add_comment(self, issue_id: str, body: str) -> None:
        self._run_cli(
            ["gh", "issue", "comment", issue_id, "-R", f"{self.host}/{self.repo}", "--body", body],
            env_overrides=self._env(),
            parse_json=False,
        )

    def create_pull_request(
        self, title: str, body: str, base: str, head: str, draft: bool = False,
        assignees: list[str] | None = None,
    ) -> str:
        argv = [
            "gh", "pr", "create",
            "-R", f"{self.host}/{self.repo}",
            "--base", base,
            "--head", head,
            "--title", title,
            "--body", body,
        ]
        if draft:
            argv.append("--draft")
        for login in assignees or []:
            argv += ["--assignee", login]
        url = self._run_cli(argv, env_overrides=self._env(), parse_json=False)
        return str(url).strip()
