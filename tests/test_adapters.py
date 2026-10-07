import json
import subprocess

import pytest

from harness.adapters.base import AdapterError
from harness.adapters.github import GitHubAdapter
from harness.adapters.gitlab import GitLabAdapter
from harness.adapters.jira import JiraAdapter


def _mock_completed(stdout: str) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=[], returncode=0, stdout=stdout, stderr="")


class TestGitHubAdapter:
    def test_get_issue_parses_fields(self, mocker, gh_issue_json):
        mocker.patch("subprocess.run", return_value=_mock_completed(json.dumps(gh_issue_json)))
        adapter = GitHubAdapter("github.helix.gsa.gov", "org/repo")
        issue = adapter.get_issue("12")

        assert issue.title == "Migrate core auth service"
        assert issue.status == "OPEN"
        assert "compliance:moderate" in issue.labels
        assert issue.assignees == ["jdoe"]

    def test_get_issue_closed_state(self, mocker, gh_issue_json):
        gh_issue_json["state"] = "CLOSED"
        mocker.patch("subprocess.run", return_value=_mock_completed(json.dumps(gh_issue_json)))
        adapter = GitHubAdapter("github.com", "org/repo")
        issue = adapter.get_issue("12")
        assert issue.status == "CLOSED"

    def test_create_issue_uses_gh_host_env(self, mocker):
        run_mock = mocker.patch(
            "subprocess.run", return_value=_mock_completed("https://github.helix.gsa.gov/org/repo/issues/4\n")
        )
        adapter = GitHubAdapter("github.helix.gsa.gov", "org/repo")
        from harness.models import CanonicalIssue

        result = adapter.create_issue(CanonicalIssue.create_new(title="T", body_markdown="B"))

        assert result == "https://github.helix.gsa.gov/org/repo/issues/4"
        called_env = run_mock.call_args.kwargs["env"]
        assert called_env["GH_HOST"] == "github.helix.gsa.gov"

    def test_cli_failure_raises_adapter_error(self, mocker):
        mocker.patch(
            "subprocess.run",
            side_effect=subprocess.CalledProcessError(1, ["gh"], stderr="not found"),
        )
        adapter = GitHubAdapter("github.com", "org/repo")
        with pytest.raises(AdapterError):
            adapter.get_issue("999")

    def test_cli_failure_does_not_expose_arguments_or_stderr(self, mocker):
        secret = "sensitive issue body"
        mocker.patch(
            "subprocess.run",
            side_effect=subprocess.CalledProcessError(2, ["gh"], stderr=f"rejected: {secret}"),
        )
        adapter = GitHubAdapter("github.com", "org/repo")
        with pytest.raises(AdapterError) as raised:
            adapter._run_cli(["gh", "issue", "create", "--body", secret])
        assert str(raised.value) == "Command failed (gh issue create), exit 2"
        assert secret not in str(raised.value)

    def test_non_json_output_does_not_expose_response_body(self, mocker):
        secret = "sensitive provider response"
        mocker.patch("subprocess.run", return_value=_mock_completed(secret))
        adapter = GitHubAdapter("github.com", "org/repo")
        with pytest.raises(AdapterError) as raised:
            adapter._run_cli(["gh", "issue", "view", "1"])
        assert str(raised.value) == "Non-JSON output from gh issue view"
        assert secret not in str(raised.value)


class TestGitLabAdapter:
    def test_get_issue_parses_fields(self, mocker, glab_issue_json):
        mocker.patch("subprocess.run", return_value=_mock_completed(json.dumps(glab_issue_json)))
        adapter = GitLabAdapter("workshop.cloud.gov", "group/project")
        issue = adapter.get_issue("88")

        assert issue.title == "Migrate core auth service"
        assert issue.status == "OPEN"
        assert issue.assignees == ["jdoe"]

    def test_get_issue_closed_state(self, mocker, glab_issue_json):
        glab_issue_json["state"] = "closed"
        mocker.patch("subprocess.run", return_value=_mock_completed(json.dumps(glab_issue_json)))
        adapter = GitLabAdapter("workshop.cloud.gov", "group/project")
        issue = adapter.get_issue("88")
        assert issue.status == "CLOSED"

    def test_create_issue_uses_gitlab_host_env(self, mocker):
        run_mock = mocker.patch(
            "subprocess.run", return_value=_mock_completed("https://workshop.cloud.gov/group/project/-/issues/5\n")
        )
        adapter = GitLabAdapter("workshop.cloud.gov", "group/project")
        from harness.models import CanonicalIssue

        adapter.create_issue(CanonicalIssue.create_new(title="T", body_markdown="B"))
        called_env = run_mock.call_args.kwargs["env"]
        assert called_env["GITLAB_HOST"] == "workshop.cloud.gov"


class TestJiraAdapter:
    def test_get_issue_parses_adf_body(self, mocker, jira_issue_json):
        mocker.patch("subprocess.run", return_value=_mock_completed(json.dumps(jira_issue_json)))
        adapter = JiraAdapter("https://gsa-standard.atlassian-us-gov-mod.net", "PROJ")
        issue = adapter.get_issue("PROJ-402")

        assert issue.title == "Migrate core auth service"
        assert "Summary" in issue.body_markdown
        assert issue.status == "OPEN"
        assert issue.priority == "HIGH"

    def test_get_issue_done_status_maps_to_closed(self, mocker, jira_issue_json):
        jira_issue_json["fields"]["status"]["name"] = "Done"
        mocker.patch("subprocess.run", return_value=_mock_completed(json.dumps(jira_issue_json)))
        adapter = JiraAdapter("https://gsa-standard.atlassian-us-gov-mod.net", "PROJ")
        issue = adapter.get_issue("PROJ-402")
        assert issue.status == "CLOSED"

    def test_update_issue_transitions_status(self, mocker):
        run_mock = mocker.patch("subprocess.run", return_value=_mock_completed(""))
        adapter = JiraAdapter("https://gsa-standard.atlassian-us-gov-mod.net", "PROJ")
        from harness.models import CanonicalIssue

        adapter.update_issue(
            "PROJ-402", CanonicalIssue.create_new(title="T", body_markdown="B", status="CLOSED")
        )

        move_calls = [c for c in run_mock.call_args_list if "move" in c.args[0]]
        assert len(move_calls) == 1
        assert move_calls[0].args[0][-1] == "Done"
