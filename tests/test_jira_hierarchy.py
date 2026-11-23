import pytest
from typer.testing import CliRunner

from harness import cli
from harness.adapters.acli_jira import AcliJiraAdapter
from harness.adapters.base import AdapterError
from harness.adapters.jira_rest import JiraRestHierarchyAdapter


def test_rest_hierarchy_reads_type_and_parent(mocker):
    adapter = JiraRestHierarchyAdapter("https://jira.example", "u", "t", "TEST")
    request = mocker.patch.object(
        adapter,
        "_request",
        return_value={
            "fields": {
                "issuetype": {"name": "Story"},
                "parent": {"key": "TEST-1"},
            }
        },
    )

    assert adapter.get_hierarchy("TEST-2") == ("Story", "TEST-1")
    assert request.call_args.args[0] == "GET"


def test_rest_hierarchy_sets_parent_only(mocker):
    adapter = JiraRestHierarchyAdapter("https://jira.example", "u", "t", "TEST")
    request = mocker.patch.object(adapter, "_request", return_value={})

    adapter.set_parent("TEST-2", "TEST-1")

    assert request.call_args.args == (
        "PUT",
        "/rest/api/3/issue/TEST-2",
        {"fields": {"parent": {"key": "TEST-1"}}},
    )


def test_rest_hierarchy_accepts_empty_successful_parent_update(mocker):
    response = mocker.MagicMock()
    response.__enter__.return_value = response
    response.read.return_value = b""
    mocker.patch("urllib.request.urlopen", return_value=response)
    adapter = JiraRestHierarchyAdapter("https://jira.example", "u", "t", "TEST")

    adapter.set_parent("TEST-2", "TEST-1")


def test_rest_hierarchy_rejects_non_json_nonempty_update_response(mocker):
    response = mocker.MagicMock()
    response.__enter__.return_value = response
    response.read.return_value = b"not-json"
    mocker.patch("urllib.request.urlopen", return_value=response)
    adapter = JiraRestHierarchyAdapter("https://jira.example", "u", "t", "TEST")

    with pytest.raises(AdapterError, match="Jira REST board query failed"):
        adapter.set_parent("TEST-2", "TEST-1")


def test_hierarchy_dry_run_requires_expected_current_state(
    mocker, monkeypatch, tmp_path
):
    monkeypatch.setenv("JIRA_INSTANCE_URL", "https://jira.example")
    monkeypatch.setenv("JIRA_EMAIL", "u@example")
    monkeypatch.setenv("JIRA_API_TOKEN", "token")
    mocker.patch.object(
        cli, "_runtime_config", return_value=tmp_path / "omni-project.toml"
    )
    mocker.patch.object(cli, "_load_dotenv")
    mocker.patch.object(
        cli, "load_config", return_value={"jira": {"project_key": "TEST"}}
    )
    mocker.patch.object(
        JiraRestHierarchyAdapter, "get_hierarchy", return_value=("Epic", None)
    )
    set_parent = mocker.patch.object(JiraRestHierarchyAdapter, "set_parent")

    result = CliRunner().invoke(
        cli.app,
        ["jira-hierarchy", "TEST-2", "--expected-type", "Epic", "--parent", "TEST-1"],
    )

    assert result.exit_code == 0, result.output
    assert "dry-run" in result.output
    set_parent.assert_not_called()


def test_hierarchy_apply_changes_type_then_parent_and_verifies(
    mocker, monkeypatch, tmp_path
):
    monkeypatch.setenv("JIRA_INSTANCE_URL", "https://jira.example")
    monkeypatch.setenv("JIRA_EMAIL", "u@example")
    monkeypatch.setenv("JIRA_API_TOKEN", "token")
    mocker.patch.object(
        cli, "_runtime_config", return_value=tmp_path / "omni-project.toml"
    )
    mocker.patch.object(cli, "_load_dotenv")
    mocker.patch.object(
        cli, "load_config", return_value={"jira": {"project_key": "TEST"}}
    )
    hierarchy = mocker.patch.object(
        JiraRestHierarchyAdapter,
        "get_hierarchy",
        side_effect=[("Epic", None), ("Story", None), ("Story", "TEST-1")],
    )
    change_type = mocker.patch.object(AcliJiraAdapter, "change_type")
    set_parent = mocker.patch.object(JiraRestHierarchyAdapter, "set_parent")

    result = CliRunner().invoke(
        cli.app,
        [
            "jira-hierarchy",
            "TEST-2",
            "--expected-type",
            "Epic",
            "--parent",
            "TEST-1",
            "--issue-type",
            "Story",
            "--apply",
        ],
    )

    assert result.exit_code == 0, result.output
    change_type.assert_called_once_with("TEST-2", "Story")
    set_parent.assert_called_once_with("TEST-2", "TEST-1")
    assert hierarchy.call_count == 3
