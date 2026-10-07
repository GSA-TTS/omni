import subprocess

from harness.adapters.acli_jira import AcliJiraAdapter
from harness.adapters.base import CliMetrics
from harness.adapters.github import GitHubAdapter
from harness.testing.bench import OpMetric, render_matrix

_WORKITEM = (
    '{"fields": {"summary": "s", "status": {"statusCategory": {"name": "To Do"}}, '
    '"assignee": null, "labels": []}}'
)


def _ok(stdout: str = "") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=[], returncode=0, stdout=stdout, stderr="")


def test_metrics_count_cli_calls(mocker):
    mocker.patch("subprocess.run", return_value=_ok(_WORKITEM))
    adapter = AcliJiraAdapter("acli", "FPDF")
    adapter.metrics = CliMetrics()
    adapter.get_issue("FPDF-1")
    assert adapter.metrics.count == 1


def test_acli_get_issue_is_single_view_call_regression_guard(mocker):
    """Guard the N+1 regression: get_issue must make exactly one `workitem view`."""
    mocker.patch("subprocess.run", return_value=_ok(_WORKITEM))
    adapter = AcliJiraAdapter("acli", "FPDF")
    adapter.metrics = CliMetrics()
    adapter.get_issue("FPDF-1")
    assert adapter.metrics.count_matching("workitem view") == 1


def test_view_cache_prevents_repeat_calls_across_accessors(mocker):
    """status_category/labels/assignee reuse the cached view -> still one call."""
    mocker.patch("subprocess.run", return_value=_ok(_WORKITEM))
    adapter = AcliJiraAdapter("acli", "FPDF")
    adapter.metrics = CliMetrics()
    adapter.status_category("FPDF-1")
    adapter.labels("FPDF-1")
    adapter.current_assignee_email("FPDF-1")
    assert adapter.metrics.count_matching("workitem view") == 1


def test_metrics_off_by_default(mocker):
    mocker.patch("subprocess.run", return_value=_ok(_WORKITEM))
    adapter = AcliJiraAdapter("acli", "FPDF")
    assert adapter.metrics is None
    adapter.get_issue("FPDF-1")  # must not raise without a collector


def test_render_matrix_shapes_output():
    op = OpMetric("jira-mod", "get_issue", calls=1, latencies=[0.01, 0.02, 0.03])
    out = render_matrix([op])
    assert "jira-mod" in out
    assert "get_issue" in out
    assert "p50(ms)" in out


def test_github_get_issue_single_call(mocker):
    mocker.patch(
        "subprocess.run",
        return_value=_ok('{"title":"t","body":"b","state":"OPEN","labels":[],"assignees":[]}'),
    )
    adapter = GitHubAdapter("github.com", "o/r")
    adapter.metrics = CliMetrics()
    adapter.get_issue("1")
    assert adapter.metrics.count == 1
