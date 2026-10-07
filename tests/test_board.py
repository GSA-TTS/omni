import json
import subprocess

from harness.adapters.acli_jira import AcliJiraAdapter
from harness.adapters.github import GitHubAdapter
from harness.adapters.gitlab import GitLabAdapter
from harness.engine.board import IssueBoard, render_boards
from harness.models import OpenIssue


def _completed(data) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess([], 0, json.dumps(data), "")


def test_github_list_combines_authored_and_assigned_without_duplicates(mocker):
    authored = [{"number": 2, "title": "Two", "body": "B", "labels": [], "url": "https://host/o/r/issues/2"}]
    assigned = [
        authored[0],
        {"number": 1, "title": "One", "body": "A", "labels": [{"name": "bug"}], "url": "https://host/o/r/issues/1"},
    ]
    run = mocker.patch("subprocess.run", side_effect=[_completed(authored), _completed(assigned)])

    issues = GitHubAdapter("host", "o/r").list_open_authored_or_assigned(25)

    assert [issue.issue_id for issue in issues] == ["1", "2"]
    assert issues[0].labels == ("bug",)
    assert "--author" in run.call_args_list[0].args[0]
    assert "--assignee" in run.call_args_list[1].args[0]


def test_gitlab_list_uses_current_user_scopes_and_encoded_project(mocker):
    item = {"iid": 3, "title": "Three", "description": "Body", "labels": ["security"], "web_url": "https://gl/g/r/-/issues/3"}
    run = mocker.patch("subprocess.run", side_effect=[_completed([item]), _completed([item])])

    issues = GitLabAdapter("gl", "group/repo").list_open_authored_or_assigned(10)

    assert len(issues) == 1
    assert "projects/group%2Frepo/issues" in run.call_args_list[0].args[0][2]
    assert "scope=created_by_me" in run.call_args_list[0].args[0][2]
    assert "scope=assigned_to_me" in run.call_args_list[1].args[0][2]


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

    issues = AcliJiraAdapter("acli", "TEST").list_open_authored_or_assigned("https://jira.example", 20)

    assert issues[0].body == "ADF body"
    assert issues[0].url == "https://jira.example/browse/TEST-2"
    argv = run.call_args.args[0]
    assert "assignee = currentUser() OR reporter = currentUser()" in argv[argv.index("--jql") + 1]


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

    rendered = render_boards(boards, body_limit=24)

    assert rendered.count("```mermaid") == 4
    assert "ticketBaseUrl: 'https://github.com/o/r/issues/#TICKET#'" in rendered
    assert "@{ ticket: '12' }" in rendered
    assert '[12](https://github.com/o/r/issues/12)' in rendered
    assert "&quot;unsafe&quot;" in rendered
    assert "&lt;markup&gt;" not in rendered  # truncated before this content
    assert "Provider query failed; see stderr" in rendered
