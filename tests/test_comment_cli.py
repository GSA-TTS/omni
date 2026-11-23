import pytest
from typer import BadParameter
from typer.testing import CliRunner

from harness import cli
from harness.adapters.acli_jira import AcliJiraAdapter


def test_comment_uses_acli_adapter_append_only(mocker):
    adapter = mocker.Mock(spec=AcliJiraAdapter)
    mocker.patch.object(cli, "_resolve_adapter", return_value=adapter)

    result = CliRunner().invoke(
        cli.app,
        ["comment", "FPDF-844", "Review complete", "--to", "jira-mod"],
    )

    assert result.exit_code == 0, result.output
    adapter.append_comment.assert_called_once_with("FPDF-844", "Review complete")
    assert "Comment appended on jira-mod: FPDF-844" in result.output


def test_comment_rejects_non_jira_target():
    with pytest.raises(BadParameter, match="only --to jira-mod"):
        cli.comment("FPDF-844", "Review complete", to="gh-tts")


def test_comment_rejects_blank_body():
    with pytest.raises(BadParameter, match="body cannot be empty"):
        cli.comment("FPDF-844", "  ")
