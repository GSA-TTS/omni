import json
import subprocess

from harness.adapters.acli_jira import AcliJiraAdapter
from harness.adapters.github import GitHubAdapter
from harness.adapters.gitlab import GitLabAdapter
from harness.engine.board import IssueBoard, render_boards
from harness.models import IssueQuery, OpenIssue


def _completed(data) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess([], 0, json.dumps(data), "")


def test_github_list_combines_authored_and_assigned_without_duplicates(mocker):
    authored = [{"number": 2, "title": "Two", "body": "B", "labels": [], "url": "https://host/o/r/issues/2"}]
    assigned = [
        authored[0],
        {"number": 1, "title": "One", "body": "A", "labels": [{"name": "bug"}], "url": "https://host/o/r/issues/1"},
    ]
    run = mocker.patch("subprocess.run", side_effect=[_completed(authored), _completed(assigned)])

    query = IssueQuery(limit=25)
    issues = GitHubAdapter("host", "o/r").list_issues(query)

    assert [issue.issue_id for issue in issues] == ["1", "2"]
    assert issues[0].labels == ("bug",)
    assert "--author" in run.call_args_list[0].args[0]
    assert "--assignee" in run.call_args_list[1].args[0]


def test_github_list_propagates_user_state_labels_and_search(mocker):
    run = mocker.patch("subprocess.run", return_value=_completed([]))
    query = IssueQuery(("assigned",), ("other-user",), "closed", ("bug", "risk"), "token refresh", 15)

    GitHubAdapter("host", "o/r").list_issues(query)

    argv = run.call_args.args[0]
    assert ["--state", "closed"] == argv[argv.index("--state"):argv.index("--state") + 2]
    assert ["--assignee", "other-user"] == argv[argv.index("--assignee"):argv.index("--assignee") + 2]
    assert argv.count("--label") == 2
    assert ["--search", "token refresh"] == argv[argv.index("--search"):]


def test_gitlab_list_uses_current_user_scopes_and_encoded_project(mocker):
    item = {"iid": 3, "title": "Three", "description": "Body", "labels": ["security"], "web_url": "https://gl/g/r/-/issues/3"}
    run = mocker.patch("subprocess.run", side_effect=[_completed([item]), _completed([item])])

    issues = GitLabAdapter("gl", "group/repo").list_issues(IssueQuery(limit=10))

    assert len(issues) == 1
    assert "projects/group%2Frepo/issues" in run.call_args_list[0].args[0][2]
    assert "scope=created_by_me" in run.call_args_list[0].args[0][2]
    assert "scope=assigned_to_me" in run.call_args_list[1].args[0][2]


def test_gitlab_list_uses_named_user_and_filters(mocker):
    run = mocker.patch("subprocess.run", return_value=_completed([]))
    query = IssueQuery(("authored",), ("other-user",), "all", ("bug", "risk"), "token refresh", 15)

    GitLabAdapter("gl", "group/repo").list_issues(query)

    endpoint = run.call_args.args[0][2]
    assert "author_username=other-user" in endpoint
    assert "state=all" in endpoint
    assert "labels=bug%2Crisk" in endpoint
    assert "search=token+refresh" in endpoint


def test_jira_list_uses_current_user_jql_and_flattens_adf(mocker):
    data = [
        {
            "key": "TEST-2",
            "fields": {
                "summary": "Jira issue",
                "description": {"type": "doc", "content": [{"type": "paragraph", "content": [{"text": "ADF body"}]}]},
                "labels": ["risk"],
            },
        }
    ]
    run = mocker.patch("subprocess.run", return_value=_completed(data))

    issues = AcliJiraAdapter("acli", "TEST").list_issues("https://jira.example", IssueQuery(limit=20))

    assert issues[0].body == "ADF body"
    assert issues[0].url == "https://jira.example/browse/TEST-2"
    argv = run.call_args.args[0]
    jql = argv[argv.index("--jql") + 1]
    assert "reporter = currentUser()" in jql
    assert "assignee = currentUser()" in jql


def test_jira_list_escapes_named_users_and_applies_filters(mocker):
    run = mocker.patch("subprocess.run", return_value=_completed([]))
    query = IssueQuery(("assigned",), ('person"@agency.gov',), "closed", ("risk",), "token refresh", 10)

    AcliJiraAdapter("acli", "TEST").list_issues("https://jira.example", query)

    argv = run.call_args.args[0]
    jql = argv[argv.index("--jql") + 1]
    assert 'assignee = "person\\"@agency.gov"' in jql
    assert "statusCategory = Done" in jql
    assert 'labels = "risk"' in jql
    assert 'text ~ "token refresh"' in jql


def test_renderer_creates_separate_boards_with_direct_links_and_safe_text():
    issue = OpenIssue(
        provider="github.com",
        issue_id="12",
        title='Fix "unsafe" [title]',
        body="A body with | pipes and <markup> that is deliberately long",
        labels=("bug", "security"),
        url="https://github.com/o/r/issues/12",
    )
    boards = [
        IssueBoard("GitHub.com", "github_com", "https://github.com/o/r/issues/#TICKET#", (issue,)),
        IssueBoard("GitHub Helix", "github_helix", "https://helix/o/r/issues/#TICKET#", ()),
        IssueBoard("GitLab", "gitlab", "https://gl/o/r/-/issues/#TICKET#", (), "unavailable"),
        IssueBoard("Jira", "jira", "https://jira/browse/#TICKET#", ()),
    ]

    rendered = render_boards(
        boards,
        body_limit=24,
        filters={"Relationships": "assigned", "Users": "@me"},
        generated_at="2026-10-07T12:00:00+00:00",
    )

    assert rendered.count("```mermaid") == 4
    assert "ticketBaseUrl: 'https://github.com/o/r/issues/#TICKET#'" in rendered
    assert "@{ ticket: '12' }" in rendered
    assert '[12](https://github.com/o/r/issues/12)' in rendered
    assert "&quot;unsafe&quot;" in rendered
    assert "&lt;markup&gt;" not in rendered  # truncated before this content
    assert "Provider query failed: unavailable" in rendered
    assert "Generated: `2026-10-07T12:00:00+00:00`" in rendered
    assert "Total issues: **1**" in rendered
    assert "**Relationships:** assigned" in rendered
