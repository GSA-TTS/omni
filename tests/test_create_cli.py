import pytest
from typer import BadParameter
from typer.testing import CliRunner

from harness import cli
from harness.adapters.base import AdapterError, BaseIssueAdapter
from harness.models import CanonicalIssue


class _RecordingAdapter(BaseIssueAdapter):
    def __init__(self) -> None:
        self.issue: CanonicalIssue | None = None

    def get_issue(self, issue_id: str) -> CanonicalIssue:
        raise AdapterError("not used")

    def create_issue(self, issue: CanonicalIssue) -> str:
        self.issue = issue
        return "FPDF-900"

    def update_issue(self, issue_id: str, issue: CanonicalIssue) -> None:
        raise AdapterError("not used")


def test_create_forwards_jira_work_item_fields_only_to_jira(mocker):
    adapter = _RecordingAdapter()
    mocker.patch.object(cli, "_resolve_adapter", return_value=adapter)
    mocker.patch.object(cli, "_resolve_assignees", return_value=[])

    result = CliRunner().invoke(
        cli.app,
        [
            "create",
            "DQX remediation",
            "Acceptance criteria",
            "--to",
            "jira-mod",
            "--jira-type",
            "Epic",
        ],
    )

    assert result.exit_code == 0, result.output
    assert adapter.issue is not None
    assert adapter.issue.jira_issue_type == "Epic"
    assert adapter.issue.jira_parent is None


def test_create_rejects_jira_options_without_jira_target():
    result = CliRunner().invoke(
        cli.app,
        [
            "create",
            "DQX remediation",
            "Acceptance criteria",
            "--to",
            "gh-tts",
            "--parent",
            "FPDF-900",
        ],
    )

    assert result.exit_code != 0

    with pytest.raises(BadParameter, match="require --to jira-mod"):
        cli.create(
            "DQX remediation",
            "Acceptance criteria",
            ["gh-tts"],
            [],
            parent="FPDF-900",
        )
