import subprocess

import pytest

from harness.adapters.base import AdapterError
from harness.adapters.github import GitHubAdapter
from harness.adapters.gitlab import GitLabAdapter
from harness.adapters.jira import JiraAdapter


def _ok(stdout: str) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=[], returncode=0, stdout=stdout, stderr="")


class TestGitHubPR:
    def test_create_pr_builds_expected_argv(self, mocker):
        run_mock = mocker.patch(
            "subprocess.run", return_value=_ok("https://github.com/o/r/pull/7\n")
        )
        adapter = GitHubAdapter("github.com", "o/r")
        url = adapter.create_pull_request("T", "B", base="main", head="feat/x")

        assert url == "https://github.com/o/r/pull/7"
        argv = run_mock.call_args.args[0]
        assert argv[:3] == ["gh", "pr", "create"]
        assert "--base" in argv and "main" in argv
        assert "--head" in argv and "feat/x" in argv
        assert "--draft" not in argv

    def test_draft_flag(self, mocker):
        run_mock = mocker.patch("subprocess.run", return_value=_ok("url\n"))
        GitHubAdapter("github.com", "o/r").create_pull_request("T", "B", base="main", head="h", draft=True)
        assert "--draft" in run_mock.call_args.args[0]

    def test_assignees_passed(self, mocker):
        run_mock = mocker.patch("subprocess.run", return_value=_ok("url\n"))
        GitHubAdapter("github.com", "o/r").create_pull_request(
            "T", "B", base="main", head="h", assignees=["jjediny"]
        )
        argv = run_mock.call_args.args[0]
        assert "--assignee" in argv and "jjediny" in argv


class TestGitLabMR:
    def test_create_mr_uses_source_and_target_branch(self, mocker):
        run_mock = mocker.patch(
            "subprocess.run", return_value=_ok("https://gl/o/r/-/merge_requests/3\n")
        )
        url = GitLabAdapter("workshop.cloud.gov", "g/p").create_pull_request(
            "T", "B", base="main", head="feat/x"
        )
        assert url.endswith("/merge_requests/3")
        argv = run_mock.call_args.args[0]
        assert argv[:3] == ["glab", "mr", "create"]
        assert "--source-branch" in argv and "feat/x" in argv
        assert "--target-branch" in argv and "main" in argv
        assert "--yes" in argv  # non-interactive


class TestJiraNoPR:
    def test_jira_pr_unsupported(self):
        adapter = JiraAdapter("https://example", "PROJ")
        with pytest.raises(AdapterError, match="does not support pull requests"):
            adapter.create_pull_request("T", "B", base="main", head="h")
