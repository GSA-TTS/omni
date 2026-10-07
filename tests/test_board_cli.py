from pathlib import Path

import pytest
import typer

from harness import cli
from harness.engine import board as board_engine
from harness.adapters.base import AdapterError
from harness.models import OpenIssue


class _Adapter:
    def __init__(self, *args, fail: bool = False):
        self.fail = fail

    queries = []

    def list_issues(self, *args):
        self.queries.append(args[-1])
        if self.fail:
            raise AdapterError("query failed")
        return [OpenIssue("provider", "1", "Title", "Body", ("bug",), "https://example/issues/1")]


class _JiraAdapter(_Adapter):
    def list_issues(self, base_url, query):
        self.queries.append(query)
        if self.fail:
            raise AdapterError("query failed")
        return [OpenIssue("jira-mod", "TEST-1", "Title", "Body", ("bug",), f"{base_url}/browse/TEST-1")]


def _config() -> dict:
    return {
        "github": {"org": "org", "repos": ["repo"]},
        "gitlab": {"host": "gitlab.example"},
        "jira": {"project_key": "TEST", "base_url": "https://jira.example"},
        "board": {
            "gh_tts_url": "https://boards.example/public/#TICKET#",
            "gh_helix_url": "https://boards.example/helix/#TICKET#",
            "gl_cg_url": "https://boards.example/gitlab/#TICKET#",
            "jira_mod_url": "https://boards.example/jira/#TICKET#",
        },
    }


def test_board_writes_four_provider_boards(mocker, tmp_path, monkeypatch):
    monkeypatch.setenv("GH_TTS_REPO", "org/public")
    monkeypatch.setenv("GH_HELIX_REPO", "org/helix")
    monkeypatch.setenv("GL_CG_REPO", "group/repo")
    mocker.patch.object(cli, "_load_dotenv")
    mocker.patch.object(cli, "load_config", return_value=_config())
    mocker.patch.object(board_engine, "GitHubAdapter", _Adapter)
    mocker.patch.object(board_engine, "GitLabAdapter", _Adapter)
    mocker.patch.object(board_engine, "AcliJiraAdapter", _JiraAdapter)
    output = tmp_path / "board.md"

    _Adapter.queries = []
    cli.board(
        tmp_path / "omni-project.toml", output, ["assigned"], ["@me"], "open",
        ["bug"], "token", [], 25, 80,
    )

    rendered = output.read_text()
    assert rendered.count("```mermaid") == 4
    assert "## GitHub.com" in rendered
    assert "## GitHub Helix" in rendered
    assert "## GitLab" in rendered
    assert "## Jira" in rendered
    assert "ticketBaseUrl: 'https://boards.example/public/#TICKET#'" in rendered
    assert "ticketBaseUrl: 'https://boards.example/helix/#TICKET#'" in rendered
    assert "ticketBaseUrl: 'https://boards.example/gitlab/#TICKET#'" in rendered
    assert "ticketBaseUrl: 'https://boards.example/jira/#TICKET#'" in rendered
    assert "[1](https://boards.example/public/1)" in rendered
    assert "# Open Issues Context" in rendered
    assert "**Relationships:** assigned" in rendered
    assert "**Labels:** bug" in rendered
    assert all(query.relationships == ("assigned",) for query in _Adapter.queries)
    assert all(query.search == "token" for query in _Adapter.queries)


def test_board_renders_remaining_providers_and_exits_nonzero_on_failure(mocker, tmp_path, monkeypatch):
    monkeypatch.setenv("GH_TTS_REPO", "org/public")
    monkeypatch.setenv("GH_HELIX_REPO", "org/helix")
    monkeypatch.setenv("GL_CG_REPO", "group/repo")
    mocker.patch.object(cli, "_load_dotenv")
    mocker.patch.object(cli, "load_config", return_value=_config())
    mocker.patch.object(board_engine, "GitHubAdapter", lambda *args: _Adapter(fail=args[0] == "github.com"))
    mocker.patch.object(board_engine, "GitLabAdapter", _Adapter)
    mocker.patch.object(board_engine, "AcliJiraAdapter", _JiraAdapter)
    output = tmp_path / "board.md"

    with pytest.raises(typer.Exit) as raised:
        cli.board(
            Path(tmp_path / "omni-project.toml"), output, [], [], "open", [], None, [], 25, 80,
        )

    assert raised.value.exit_code == 1
    assert output.read_text().count("```mermaid") == 4


def test_board_limits_report_to_selected_targets(mocker, tmp_path, monkeypatch):
    monkeypatch.setenv("GH_TTS_REPO", "org/public")
    mocker.patch.object(cli, "_load_dotenv")
    mocker.patch.object(cli, "load_config", return_value=_config())
    mocker.patch.object(board_engine, "GitHubAdapter", _Adapter)
    output = tmp_path / "board.md"

    cli.board(
        tmp_path / "omni-project.toml", output, [], [], "all", [], None, ["gh-tts"], 10, 40,
    )

    rendered = output.read_text()
    assert rendered.count("```mermaid") == 1
    assert "### GitHub.com" in rendered
    assert "GitHub Helix" not in rendered


def test_board_rejects_unmapped_email_without_querying_provider(mocker, tmp_path, monkeypatch):
    monkeypatch.setenv("GH_TTS_REPO", "org/public")
    mocker.patch.object(cli, "_load_dotenv")
    mocker.patch.object(cli, "load_config", return_value=_config())
    adapter = mocker.patch.object(board_engine, "GitHubAdapter")
    output = tmp_path / "board.md"

    with pytest.raises(typer.Exit) as raised:
        cli.board(
            tmp_path / "omni-project.toml", output, [], ["missing@agency.gov"],
            "open", [], None, ["gh-tts"], 10, 40,
        )

    assert raised.value.exit_code == 1
    adapter.return_value.list_issues.assert_not_called()
    assert "Provider query failed: one or more email users have no roster mapping" in output.read_text()


def test_board_derives_repo_from_configured_ticket_url(mocker, tmp_path, monkeypatch):
    monkeypatch.delenv("GH_TTS_REPO", raising=False)
    mocker.patch.object(cli, "_load_dotenv")
    config = _config()
    config["board"]["gh_tts_url"] = "https://github.com/org/public/issues/#TICKET#"
    mocker.patch.object(cli, "load_config", return_value=config)
    adapter = mocker.patch.object(board_engine, "GitHubAdapter", autospec=True)
    adapter.return_value.list_issues.return_value = []
    output = tmp_path / "board.md"

    cli.board(
        tmp_path / "omni-project.toml", output, [], [], "open", [], None,
        ["gh-tts"], 10, 40,
    )

    adapter.assert_called_once_with("github.com", "org/public")
    assert output.exists()


def test_board_default_current_user_does_not_load_roster(mocker, tmp_path, monkeypatch):
    monkeypatch.setenv("GH_TTS_REPO", "org/public")
    mocker.patch.object(cli, "_load_dotenv")
    mocker.patch.object(cli, "load_config", return_value=_config())
    roster = mocker.patch.object(cli.UserRoster, "load")
    mocker.patch.object(board_engine, "GitHubAdapter", _Adapter)

    cli.board(
        tmp_path / "omni-project.toml", tmp_path / "board.md", [], [], "open",
        [], None, ["gh-tts"], 10, 40,
    )

    roster.assert_not_called()


def test_board_rejects_limit_above_provider_page_size(tmp_path):
    with pytest.raises(typer.BadParameter, match="cannot exceed 100"):
        cli.board(
            tmp_path / "omni-project.toml", tmp_path / "board.md", [], [], "open",
            [], None, [], 101, 40,
        )
