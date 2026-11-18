"""Read-only Jira REST adapter used when the local `acli` is unavailable."""

from __future__ import annotations

import json
import urllib.error
import urllib.request

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
        jql = build_jql(self.project_key, query)
        payload = json.dumps(
            {
                "jql": jql,
                "maxResults": min(query.limit, 100),
                "fields": ["key", "summary", "description", "labels"],
            }
        ).encode()
        request = urllib.request.Request(
            f"{self.base_url}/rest/api/3/search/jql",
            data=payload,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        manager = urllib.request.HTTPPasswordMgrWithDefaultRealm()
        manager.add_password(None, self.base_url, self.email, self.token)
        opener = urllib.request.build_opener(
            urllib.request.HTTPBasicAuthHandler(manager)
        )
        try:
            with opener.open(request, timeout=30) as response:
                data = json.load(response)
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as exc:
            raise AdapterError("Jira REST board query failed") from exc
        return issues_from_search(data, self.base_url)
