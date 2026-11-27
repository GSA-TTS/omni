"""Read-only Jira REST adapter used when the local `acli` is unavailable."""

from __future__ import annotations

import base64
import json
import urllib.error
import urllib.request
from dataclasses import replace
from urllib.parse import quote

from harness.adapters.acli_jira import build_jql, issues_from_search
from harness.adapters.base import AdapterError
from harness.models import IssueQuery, OpenIssue

_MAX_PAGE_SIZE = 100


class JiraRestBoardAdapter:
    """Fetch Jira board results with environment-injected Basic credentials.

    This adapter is intentionally read-only. It is only used by the board
    context command as a fallback for an unavailable or unauthenticated `acli`.
    """

    def __init__(self, base_url: str, email: str, token: str, project_key: str):
        self.base_url = base_url.rstrip("/")
        self.email = email
        self.token = token
        self.project_key = project_key

    def list_issues(self, query: IssueQuery) -> list[OpenIssue]:
        if "@me" in query.users:
            account_id = self._account_id()
            query = replace(
                query,
                users=tuple(
                    account_id if user == "@me" else user for user in query.users
                ),
            )
        payload = {
            "jql": build_jql(self.project_key, query),
            "fields": ["key", "summary", "description", "labels"],
        }
        issues: list[OpenIssue] = []
        next_page_token: str | None = None

        while len(issues) < query.limit:
            page_size = min(_MAX_PAGE_SIZE, query.limit - len(issues))
            page_payload = {**payload, "maxResults": page_size}
            if next_page_token is not None:
                page_payload["nextPageToken"] = next_page_token
            page = self._request("POST", "/rest/api/3/search/jql", page_payload)
            page_issues = issues_from_search(page, self.base_url)
            issues.extend(page_issues[: query.limit - len(issues)])
            next_page_token = page.get("nextPageToken")
            if (
                not page_issues
                or not isinstance(next_page_token, str)
                or not next_page_token
            ):
                break

        return issues

    def _account_id(self) -> str:
        """Resolve the authenticated user; `currentUser()` is unreliable over REST."""
        account_id = self._request("GET", "/rest/api/3/myself").get("accountId")
        if not isinstance(account_id, str) or not account_id:
            raise AdapterError("Jira REST /myself returned no accountId")
        return account_id

    def _request(self, method: str, path: str, payload: dict | None = None) -> dict:
        authorization = base64.b64encode(f"{self.email}:{self.token}".encode()).decode(
            "ascii"
        )
        headers = {
            "Accept": "application/json",
            "Authorization": f"Basic {authorization}",
        }
        if payload is not None:
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(
            f"{self.base_url}{path}",
            data=json.dumps(payload).encode() if payload is not None else None,
            headers=headers,
            method=method,
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                raw = response.read()
        except (urllib.error.URLError, TimeoutError, ValueError) as exc:
            raise AdapterError("Jira REST board query failed") from exc
        if not raw:
            return {}
        try:
            data = json.loads(raw)
        except (TypeError, ValueError) as exc:
            raise AdapterError("Jira REST board query failed") from exc
        if not isinstance(data, dict):
            raise AdapterError("Unexpected Jira REST response")
        return data


class JiraRestHierarchyAdapter(JiraRestBoardAdapter):
    """Narrow Jira REST adapter for verified parent reassignment only."""

    def get_hierarchy(self, issue_id: str) -> tuple[str, str | None]:
        data = self._request(
            "GET",
            f"/rest/api/3/issue/{quote(issue_id, safe='')}?fields=issuetype,parent",
        )
        fields = data.get("fields") or {}
        issue_type = (fields.get("issuetype") or {}).get("name")
        parent = (fields.get("parent") or {}).get("key")
        if not isinstance(issue_type, str) or not issue_type:
            raise AdapterError("Jira hierarchy read returned no issue type")
        if parent is not None and not isinstance(parent, str):
            raise AdapterError("Jira hierarchy read returned an invalid parent key")
        return issue_type, parent

    def set_parent(self, issue_id: str, parent_key: str) -> None:
        if not parent_key.strip():
            raise AdapterError("Jira parent key cannot be empty")
        self._request(
            "PUT",
            f"/rest/api/3/issue/{quote(issue_id, safe='')}",
            {"fields": {"parent": {"key": parent_key}}},
        )
