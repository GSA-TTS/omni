from pathlib import Path

import pytest
import typer

from harness import cli
from harness.adapters.base import AdapterError
from harness.models import OpenIssue


class _Adapter:
    def __init__(self, *args, fail: bool = False):
        self.fail = fail

    def list_open_authored_or_assigned(self, *args):
        if self.fail:
            raise AdapterError("query failed")
        return [OpenIssue("provider", "1", "Title", "Body", ("bug",), "https://example/issues/1")]


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
    mocker.patch.object(cli, "GitHubAdapter", _Adapter)
    mocker.patch.object(cli, "GitLabAdapter", _Adapter)
    mocker.patch.object(cli, "AcliJiraAdapter", _Adapter)
    output = tmp_path / "board.md"

    cli.board(tmp_path / "omni-project.toml", output, 25, 80)

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


def test_board_renders_remaining_providers_and_exits_nonzero_on_failure(mocker, tmp_path, monkeypatch):
    monkeypatch.setenv("GH_TTS_REPO", "org/public")
    monkeypatch.setenv("GH_HELIX_REPO", "org/helix")
    monkeypatch.setenv("GL_CG_REPO", "group/repo")
    mocker.patch.object(cli, "_load_dotenv")
    mocker.patch.object(cli, "load_config", return_value=_config())
    mocker.patch.object(cli, "GitHubAdapter", lambda *args: _Adapter(fail=args[0] == "github.com"))
    mocker.patch.object(cli, "GitLabAdapter", _Adapter)
    mocker.patch.object(cli, "AcliJiraAdapter", _Adapter)
    output = tmp_path / "board.md"

    with pytest.raises(typer.Exit) as raised:
        cli.board(Path(tmp_path / "omni-project.toml"), output, 25, 80)

    assert raised.value.exit_code == 1
    assert output.read_text().count("```mermaid") == 4
