from types import SimpleNamespace

import pytest
import typer

from harness import cli
from harness.adapters.base import AdapterError


class _IssueAdapter:
    def __init__(self, *, fail: bool = False):
        self.fail = fail

    def create_issue(self, issue):
        if self.fail:
            raise AdapterError("provider failed")
        return "created"

    def create_pull_request(self, *args, **kwargs):
        if self.fail:
            raise AdapterError("provider failed")
        return "https://example.test/pull/1"


def test_create_exits_nonzero_after_partial_failure(mocker):
    adapters = {"ok": _IssueAdapter(), "bad": _IssueAdapter(fail=True)}
    mocker.patch.object(
        cli, "_resolve_adapter", side_effect=lambda target: adapters[target]
    )
    mocker.patch.object(cli, "_resolve_assignees", return_value=[])

    with pytest.raises(typer.Exit) as raised:
        cli.create("Title", "Body", ["ok", "bad"], [])

    assert raised.value.exit_code == 1


def test_pr_exits_nonzero_after_partial_failure(mocker):
    adapters = {"ok": _IssueAdapter(), "bad": _IssueAdapter(fail=True)}
    mocker.patch.object(
        cli, "_resolve_adapter", side_effect=lambda target: adapters[target]
    )
    mocker.patch.object(cli, "_resolve_assignees", return_value=[])

    with pytest.raises(typer.Exit) as raised:
        cli.pr("Title", "main", "feature", "Body", ["ok", "bad"], False, [])

    assert raised.value.exit_code == 1


def test_github_to_jira_sync_exits_nonzero_after_ticket_failure(mocker, tmp_path):
    config = {
        "github": {"org": "example", "repos": ["repo"]},
        "jira": {"project_key": "TEST", "acli_bin": "acli"},
    }
    gh = SimpleNamespace(
        paginate_issues=lambda repo: [{"number": 1}],
        group_by_key=lambda items: {"TEST-1": items, "TEST-2": items},
    )
    mocker.patch.object(cli, "_load_dotenv")
    mocker.patch.object(cli, "load_config", return_value=config)
    mocker.patch.object(cli, "GitHubRestAdapter", return_value=gh)
    mocker.patch.object(cli, "AcliJiraAdapter", return_value=object())
    mocker.patch.object(
        cli,
        "sync_jira_from_github",
        side_effect=[
            {"gh_number": 1, "linked_count": 1, "actions": ["updated"], "errors": []},
            {
                "gh_number": 1,
                "linked_count": 1,
                "actions": [],
                "errors": ["write failed"],
            },
        ],
    )

    with pytest.raises(typer.Exit) as raised:
        cli.sync_jira_from_github_cmd(tmp_path / "config.toml", None, [], 0, False)

    assert raised.value.exit_code == 1


def test_jira_to_github_backfill_exits_nonzero_after_write_failure(mocker, tmp_path):
    config = {
        "github": {"org": "example", "repos": ["repo"]},
        "jira": {"project_key": "TEST", "acli_bin": "acli"},
    }
    gh = SimpleNamespace(
        paginate_issues=lambda repo, state: [{"number": 1, "title": "TEST-1"}],
        key_in_title=lambda title: "TEST-1",
        add_assignee=lambda *args, **kwargs: (False, "write failed"),
    )
    jira = SimpleNamespace(acli_bin="acli", _run_cli=lambda argv: [])
    mocker.patch.object(cli, "_load_dotenv")
    mocker.patch.object(cli, "load_config", return_value=config)
    mocker.patch.object(cli, "GitHubRestAdapter", return_value=gh)
    mocker.patch.object(cli, "AcliJiraAdapter", return_value=jira)
    mocker.patch.object(cli, "_email_to_login_map", return_value={})
    mocker.patch.object(
        cli,
        "plan_backfill_github_from_jira",
        return_value={
            "key": "TEST-1",
            "gh_number": 1,
            "action": "backfill",
            "login": "user",
        },
    )

    with pytest.raises(typer.Exit) as raised:
        cli.backfill_github_from_jira_cmd(tmp_path / "config.toml", None, [], 0, False)

    assert raised.value.exit_code == 1
