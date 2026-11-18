import json
import subprocess
import urllib.error

import pytest

from harness.adapters.acli_jira import AcliJiraAdapter
from harness.adapters.base import AdapterError
from harness.adapters.github import GitHubAdapter
from harness.adapters.gitlab import GitLabAdapter
from harness.adapters.jira_rest import JiraRestBoardAdapter
from harness.engine.board import IssueBoard, _collect_jira, render_boards
from harness.models import IssueQuery, OpenIssue


def _completed(data) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess([], 0, json.dumps(data), "")


def test_github_list_combines_authored_and_assigned_without_duplicates(mocker):
    authored = [
        {
            "number": 2,
            "title": "Two",
            "body": "B",
            "labels": [],
            "url": "https://host/o/r/issues/2",
        }
    ]
    assigned = [
        authored[0],
        {
            "number": 1,
            "title": "One",
            "body": "A",
            "labels": [{"name": "bug"}],
            "url": "https://host/o/r/issues/1",
        },
    ]
    run = mocker.patch(
        "subprocess.run", side_effect=[_completed(authored), _completed(assigned)]
    )

    query = IssueQuery(limit=25)
    issues = GitHubAdapter("host", "o/r").list_issues(query)

    assert [issue.issue_id for issue in issues] == ["1", "2"]
    assert issues[0].labels == ("bug",)
    assert "--author" in run.call_args_list[0].args[0]
    assert "--assignee" in run.call_args_list[1].args[0]


def test_github_list_propagates_user_state_labels_and_search(mocker):
    run = mocker.patch("subprocess.run", return_value=_completed([]))
    query = IssueQuery(
        ("assigned",), ("other-user",), "closed", ("bug", "risk"), "token refresh", 15
    )

    GitHubAdapter("host", "o/r").list_issues(query)

    argv = run.call_args.args[0]
    assert ["--state", "closed"] == argv[
        argv.index("--state") : argv.index("--state") + 2
    ]
    assert ["--assignee", "other-user"] == argv[
        argv.index("--assignee") : argv.index("--assignee") + 2
    ]
    assert argv.count("--label") == 2
    assert ["--search", "token refresh"] == argv[argv.index("--search") :]


def test_gitlab_list_uses_current_user_scopes_and_encoded_project(mocker):
    item = {
        "iid": 3,
        "title": "Three",
        "description": "Body",
        "labels": ["security"],
        "web_url": "https://gl/g/r/-/issues/3",
    }
    run = mocker.patch(
        "subprocess.run", side_effect=[_completed([item]), _completed([item])]
    )

    issues = GitLabAdapter("gl", "group/repo").list_issues(IssueQuery(limit=10))

    assert len(issues) == 1
    assert "projects/group%2Frepo/issues" in run.call_args_list[0].args[0][2]
    assert "scope=created_by_me" in run.call_args_list[0].args[0][2]
    assert "scope=assigned_to_me" in run.call_args_list[1].args[0][2]


def test_gitlab_list_uses_named_user_and_filters(mocker):
    run = mocker.patch("subprocess.run", return_value=_completed([]))
    query = IssueQuery(
        ("authored",), ("other-user",), "all", ("bug", "risk"), "token refresh", 15
    )

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
                "description": {
                    "type": "doc",
                    "content": [
                        {"type": "paragraph", "content": [{"text": "ADF body"}]}
                    ],
                },
                "labels": ["risk"],
            },
        }
    ]
    run = mocker.patch("subprocess.run", return_value=_completed(data))

    issues = AcliJiraAdapter("acli", "TEST").list_issues(
        "https://jira.example", IssueQuery(limit=20)
    )

    assert issues[0].body == "ADF body"
    assert issues[0].url == "https://jira.example/browse/TEST-2"
    argv = run.call_args.args[0]
    jql = argv[argv.index("--jql") + 1]
    assert "reporter = currentUser()" in jql
    assert "assignee = currentUser()" in jql


def test_jira_list_escapes_named_users_and_applies_filters(mocker):
    run = mocker.patch("subprocess.run", return_value=_completed([]))
    query = IssueQuery(
        ("assigned",), ('person"@agency.gov',), "closed", ("risk",), "token refresh", 10
    )

    AcliJiraAdapter("acli", "TEST").list_issues("https://jira.example", query)

    argv = run.call_args.args[0]
    jql = argv[argv.index("--jql") + 1]
    assert 'assignee = "person\\"@agency.gov"' in jql
    assert "statusCategory = Done" in jql
    assert 'labels = "risk"' in jql
    assert 'text ~ "token refresh"' in jql


@pytest.mark.parametrize(
    ("sprint", "expected"),
    [
        ("active", "sprint in openSprints()"),
        ("future", "sprint in futureSprints()"),
        ("PI Iteration 7.1", 'sprint = "PI Iteration 7.1"'),
    ],
)
def test_jira_list_applies_sprint_filter(mocker, sprint, expected):
    run = mocker.patch("subprocess.run", return_value=_completed([]))
    AcliJiraAdapter("acli", "TEST").list_issues(
        "https://jira.example", IssueQuery(("assigned",), ("@me",), sprint=sprint)
    )

    argv = run.call_args.args[0]
    assert expected in argv[argv.index("--jql") + 1]


def _urlopen_responses(mocker, *payloads):
    responses = []
    for payload in payloads:
        response = mocker.MagicMock()
        response.__enter__.return_value = response
        response.read.return_value = json.dumps(payload).encode()
        responses.append(response)
    return mocker.patch("urllib.request.urlopen", side_effect=responses)


def _rest_adapter():
    return JiraRestBoardAdapter("https://jira.example/", "u@example", "tok", "TEST")


def test_jira_rest_resolves_me_to_account_id_and_uses_basic_auth(mocker):
    urlopen = _urlopen_responses(
        mocker,
        {"accountId": "acct-1"},
        {"issues": [{"key": "TEST-1", "fields": {"summary": "s"}}]},
    )

    issues = _rest_adapter().list_issues(
        IssueQuery(("assigned",), ("@me",), sprint="active")
    )

    assert [i.issue_id for i in issues] == ["TEST-1"]
    myself, search = (call.args[0] for call in urlopen.call_args_list)
    assert myself.get_method() == "GET"
    assert myself.full_url == "https://jira.example/rest/api/3/myself"
    assert search.get_method() == "POST"
    body = json.loads(search.data)
    assert 'assignee = "acct-1"' in body["jql"]
    assert "currentUser()" not in body["jql"]
    assert "sprint in openSprints()" in body["jql"]
    assert search.get_header("Authorization").startswith("Basic ")
    assert all(call.kwargs["timeout"] == 30 for call in urlopen.call_args_list)


def test_jira_rest_skips_myself_lookup_for_named_users(mocker):
    urlopen = _urlopen_responses(mocker, {"issues": []})

    _rest_adapter().list_issues(IssueQuery(("assigned",), ("alice",)))

    assert urlopen.call_count == 1


def test_jira_rest_caps_page_size_at_100(mocker):
    urlopen = _urlopen_responses(mocker, {"issues": []})

    _rest_adapter().list_issues(IssueQuery(("assigned",), ("alice",), limit=500))

    assert json.loads(urlopen.call_args.args[0].data)["maxResults"] == 100


def test_jira_rest_rejects_missing_account_id(mocker):
    _urlopen_responses(mocker, {})

    with pytest.raises(AdapterError, match="accountId"):
        _rest_adapter().list_issues(IssueQuery(("assigned",), ("@me",)))


@pytest.mark.parametrize("error", [urllib.error.URLError("down"), TimeoutError()])
def test_jira_rest_wraps_transport_errors_without_credentials(mocker, error):
    mocker.patch("urllib.request.urlopen", side_effect=error)

    with pytest.raises(AdapterError) as exc:
        _rest_adapter().list_issues(IssueQuery(("assigned",), ("alice",)))

    assert "tok" not in str(exc.value)


def test_jira_rest_rejects_non_json_response(mocker):
    response = mocker.MagicMock()
    response.__enter__.return_value = response
    response.read.return_value = b"<html>"
    mocker.patch("urllib.request.urlopen", return_value=response)

    with pytest.raises(AdapterError):
        _rest_adapter().list_issues(IssueQuery(("assigned",), ("alice",)))


CFG = {"jira": {"base_url": "https://jira.example", "project_key": "TEST"}}


def _collect(mocker, *, acli, rest, env):
    mocker.patch.dict("os.environ", env, clear=True)
    acli_mock = mocker.patch.object(AcliJiraAdapter, "list_issues", **acli)
    rest_mock = mocker.patch.object(JiraRestBoardAdapter, "list_issues", **rest)
    roster = mocker.Mock()
    roster.resolve_issue_user.side_effect = lambda _t, value: value
    boards, errors = [], []
    _collect_jira(boards, errors, CFG, {}, roster, IssueQuery(("assigned",), ("@me",)))
    return boards, errors, acli_mock, rest_mock


CREDS = {"JIRA_EMAIL": "u@example", "JIRA_API_TOKEN": "tok"}
ISSUE = OpenIssue("jira-mod", "TEST-1", "t", "", (), "")


def test_collect_jira_uses_acli_result_without_rest_when_non_empty(mocker):
    boards, errors, _, rest = _collect(
        mocker, acli={"return_value": [ISSUE]}, rest={"return_value": []}, env=CREDS
    )

    assert [i.issue_id for i in boards[0].issues] == ["TEST-1"]
    assert errors == []
    rest.assert_not_called()


def test_collect_jira_rechecks_empty_acli_result_over_rest(mocker):
    rest_issue = OpenIssue("jira-mod", "TEST-2", "t", "", (), "")
    boards, errors, _, rest = _collect(
        mocker,
        acli={"return_value": []},
        rest={"return_value": [rest_issue]},
        env=CREDS,
    )

    assert [i.issue_id for i in boards[0].issues] == ["TEST-2"]
    assert errors == []
    rest.assert_called_once()


def test_collect_jira_keeps_empty_acli_result_when_rest_recheck_fails(mocker):
    boards, errors, _, _ = _collect(
        mocker,
        acli={"return_value": []},
        rest={"side_effect": AdapterError("boom")},
        env=CREDS,
    )

    assert boards[0].issues == () and boards[0].error is None
    assert errors == []


def test_collect_jira_empty_acli_result_without_credentials_skips_rest(mocker):
    boards, errors, _, rest = _collect(
        mocker, acli={"return_value": []}, rest={"return_value": []}, env={}
    )

    assert boards[0].issues == ()
    rest.assert_not_called()


def test_collect_jira_falls_back_to_rest_when_acli_errors(mocker):
    boards, errors, _, rest = _collect(
        mocker,
        acli={"side_effect": AdapterError("unauthenticated")},
        rest={"return_value": [ISSUE]},
        env=CREDS,
    )

    assert [i.issue_id for i in boards[0].issues] == ["TEST-1"]
    assert errors == []
    rest.assert_called_once()


def test_collect_jira_fails_closed_when_acli_errors_without_credentials(mocker):
    boards, errors, _, rest = _collect(
        mocker,
        acli={"side_effect": AdapterError("unauthenticated")},
        rest={"return_value": [ISSUE]},
        env={},
    )

    assert boards[0].issues == () and boards[0].error == "unauthenticated"
    assert errors == ["FAILED on jira-mod: unauthenticated"]
    rest.assert_not_called()


def test_collect_jira_fails_closed_when_both_providers_error(mocker):
    boards, errors, _, _ = _collect(
        mocker,
        acli={"side_effect": AdapterError("a")},
        rest={"side_effect": AdapterError("b")},
        env=CREDS,
    )

    assert boards[0].issues == ()
    assert errors == ["FAILED on jira-mod: acli and Jira REST board queries failed"]


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
        IssueBoard(
            "GitHub.com",
            "github_com",
            "https://github.com/o/r/issues/#TICKET#",
            (issue,),
        ),
        IssueBoard(
            "GitHub Helix", "github_helix", "https://helix/o/r/issues/#TICKET#", ()
        ),
        IssueBoard(
            "GitLab", "gitlab", "https://gl/o/r/-/issues/#TICKET#", (), "unavailable"
        ),
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
    assert "[12](https://github.com/o/r/issues/12)" in rendered
    assert "&quot;unsafe&quot;" in rendered
    assert "&lt;markup&gt;" not in rendered  # truncated before this content
    assert "Provider query failed: unavailable" in rendered
    assert "Generated: `2026-10-07T12:00:00+00:00`" in rendered
    assert "Total issues: **1**" in rendered
    assert "**Relationships:** assigned" in rendered
