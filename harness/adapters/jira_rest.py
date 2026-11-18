"""Read-only Jira REST adapter used when the local `acli` is unavailable."""

from __future__ import annotations

import base64
import json
import urllib.error
import urllib.request
from dataclasses import replace

from harness.adapters.acli_jira import build_jql, issues_from_search
from harness.adapters.base import AdapterError
from harness.models import IssueQuery, OpenIssue


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
            "maxResults": min(query.limit, 100),
            "fields": ["key", "summary", "description", "labels"],
        }
        return issues_from_search(
            self._request("POST", "/rest/api/3/search/jql", payload), self.base_url
        )

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
                data = json.load(response)
        except (urllib.error.URLError, TimeoutError, ValueError) as exc:
            raise AdapterError("Jira REST board query failed") from exc
        if not isinstance(data, dict):
            raise AdapterError("Unexpected Jira REST response")
        return data
