import subprocess

from harness.adapters.base import BaseIssueAdapter
from harness.adapters.github import GitHubAdapter
from harness.adapters.gitlab import GitLabAdapter
from harness.engine.reconciler import reconcile
from harness.models import CanonicalIssue


def _ok(stdout: str = "") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=[], returncode=0, stdout=stdout, stderr="")


def test_github_update_adds_labels(mocker):
    run_mock = mocker.patch("subprocess.run", return_value=_ok())
    adapter = GitHubAdapter("github.com", "o/r")
    adapter.update_issue(
        "1", CanonicalIssue.create_new("T", "B", labels=["bug", "area:sync"])
    )
    argv = run_mock.call_args_list[0].args[0]
    assert argv.count("--add-label") == 2
    assert "bug" in argv and "area:sync" in argv


def test_gitlab_update_adds_labels(mocker):
    run_mock = mocker.patch("subprocess.run", return_value=_ok())
    adapter = GitLabAdapter("workshop.cloud.gov", "g/p")
    adapter.update_issue("1", CanonicalIssue.create_new("T", "B", labels=["bug"]))
    update_argv = run_mock.call_args_list[0].args[0]
    assert "--label" in update_argv and "bug" in update_argv


class _Rec(BaseIssueAdapter):
    def __init__(self, issue):
        self.issue = issue
        self.updated = None

    def get_issue(self, _):
        return self.issue

    def create_issue(self, issue):
        raise NotImplementedError

    def update_issue(self, _id, issue):
        self.updated = issue


def test_reconcile_carries_source_labels_to_target():
    left = _Rec(CanonicalIssue.create_new("T", "B", labels=["bug", "area:sync"]))
    right = _Rec(CanonicalIssue.create_new("T", "B", labels=["stale"]))
    reconcile(left, "1", right, "2", direction="left-to-right", dry_run=False)
    assert right.updated is not None
    assert set(right.updated.labels) == {"bug", "area:sync", "stale"}


def test_label_only_delta_is_detected():
    left = CanonicalIssue.create_new("T", "B", labels=["bug"])
    right = CanonicalIssue.create_new("T", "B", labels=["bug", "extra"])
    assert left.diff(right).has_changes


def test_reconcile_ignores_target_only_labels_for_additive_convergence():
    left = _Rec(CanonicalIssue.create_new("T", "B", labels=["bug"]))
    right = _Rec(CanonicalIssue.create_new("T", "B", labels=["bug", "extra"]))
    result = reconcile(left, "1", right, "2", direction="left-to-right", dry_run=False)
    assert not result.diff.has_changes
    assert not result.applied
    assert right.updated is None


def test_reconcile_preserves_target_only_labels_when_other_fields_change():
    left = _Rec(CanonicalIssue.create_new("Source", "B", labels=["bug"]))
    right = _Rec(
        CanonicalIssue.create_new("Target", "B", labels=["bug", "human-owned"])
    )
    result = reconcile(left, "1", right, "2", direction="left-to-right", dry_run=False)
    assert result.applied
    assert right.updated is not None
    assert right.updated.labels == ["bug", "human-owned"]
