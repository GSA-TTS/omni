"""Adapter wrapping `jira-cli` (ankitpokhrel/jira-cli), targeting FedRAMP
Moderate Jira instances. Translates canonical status to the target project's
workflow transition names and markdown body to Atlassian Document Format.
"""
from __future__ import annotations

from harness.adapters.base import AdapterError, BaseIssueAdapter
from harness.models import CanonicalIssue
from harness.transformers.markdown_jira import adf_to_markdown, markdown_to_adf

# Default workflow transition names; override per-project if the Jira
# workflow uses different labels (e.g. "In Progress", "Resolved").
_STATUS_TO_TRANSITION = {
    "OPEN": "To Do",
    "CLOSED": "Done",
}


class JiraAdapter(BaseIssueAdapter):
    """Issue adapter for FedRAMP Moderate Jira via `jira-cli`."""

    def __init__(self, instance_url: str, project: str, status_map: dict[str, str] | None = None):
        self.instance_url = instance_url
        self.project = project
        self.status_map = {**_STATUS_TO_TRANSITION, **(status_map or {})}

    def _env(self) -> dict[str, str]:
        return {"JIRA_API_TOKEN_URL": self.instance_url}

    def get_issue(self, issue_id: str) -> CanonicalIssue:
        data = self._run_cli(
            ["jira", "issue", "view", issue_id, "--raw"],
            env_overrides=self._env(),
        )
        if not isinstance(data, dict):
            raise AdapterError(f"Unexpected jira-cli output for {issue_id}")
        fields = data.get("fields", {})
        status_name = (fields.get("status") or {}).get("name", "To Do")
        body = fields.get("description")
        body_markdown = adf_to_markdown(body) if isinstance(body, dict) else (body or "")
        return CanonicalIssue(
            title=fields.get("summary", ""),
            body_markdown=body_markdown,
            status="CLOSED" if status_name in ("Done", "Closed", "Resolved") else "OPEN",
            priority=(fields.get("priority") or {}).get("name"),
            labels=list(fields.get("labels", [])),
            assignees=[fields["assignee"]["displayName"]] if fields.get("assignee") else [],
        )

    def create_issue(self, issue: CanonicalIssue) -> str:
        argv = [
            "jira",
            "issue",
            "create",
            "--project",
            self.project,
            "--type",
            "Task",
            "--summary",
            issue.title,
            "--body",
            issue.body_with_anchor(),
        ]
        for label in issue.labels:
            argv += ["--label", label]
        key = self._run_cli(argv, env_overrides=self._env(), parse_json=False)
        return str(key).strip()

    def update_issue(self, issue_id: str, issue: CanonicalIssue) -> None:
        argv = [
            "jira",
            "issue",
            "edit",
            issue_id,
            "--summary",
            issue.title,
            "--body",
            issue.body_with_anchor(),
            "--no-input",
        ]
        self._run_cli(argv, env_overrides=self._env(), parse_json=False)

        transition = self.status_map.get(issue.status)
        if transition:
            self._run_cli(
                ["jira", "issue", "move", issue_id, transition],
                env_overrides=self._env(),
                parse_json=False,
            )

    def _markdown_to_adf(self, markdown: str) -> dict:
        return markdown_to_adf(markdown)
