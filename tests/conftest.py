import pytest


@pytest.fixture
def gh_issue_json() -> dict:
    return {
        "title": "Migrate core auth service",
        "body": "### Summary\nUpdate the OIDC endpoints.",
        "state": "OPEN",
        "labels": [{"name": "compliance:moderate"}, {"name": "auth"}],
        "assignees": [{"login": "jdoe"}],
        "number": 12,
    }


@pytest.fixture
def glab_issue_json() -> dict:
    return {
        "title": "Migrate core auth service",
        "description": "### Summary\nUpdate the OIDC endpoints.",
        "state": "opened",
        "labels": ["compliance:moderate", "auth"],
        "assignees": [{"username": "jdoe"}],
        "iid": 88,
    }


@pytest.fixture
def jira_issue_json() -> dict:
    return {
        "fields": {
            "summary": "Migrate core auth service",
            "description": {
                "type": "doc",
                "version": 1,
                "content": [
                    {"type": "heading", "attrs": {"level": 3}, "content": [{"type": "text", "text": "Summary"}]},
                    {
                        "type": "paragraph",
                        "content": [{"type": "text", "text": "Update the OIDC endpoints."}],
                    },
                ],
            },
            "status": {"name": "To Do"},
            "priority": {"name": "HIGH"},
            "labels": ["compliance:moderate", "auth"],
            "assignee": {"displayName": "jdoe"},
        }
    }
