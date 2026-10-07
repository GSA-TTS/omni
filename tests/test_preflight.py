import json

from harness import cli
from harness.engine.preflight import check_github, check_gitlab, check_jira


def _runner(responses):
    """Build a fake runner returning queued (rc, out) tuples per call."""
    calls = {"i": 0}

    def run(argv, env):
        rc, out = responses[calls["i"]]
        calls["i"] += 1
        return rc, out

    return run


class TestGitHub:
    def test_writable_with_issues(self):
        r = check_github("github.com", "org/repo", _runner([(0, "true\ttrue")]))
        assert r.ok
        assert "writable" in r.detail

    def test_no_push_access(self):
        r = check_github("github.com", "org/repo", _runner([(0, "true\tfalse")]))
        assert not r.ok
        assert "push" in r.detail

    def test_issues_disabled(self):
        r = check_github("github.com", "org/repo", _runner([(0, "false\ttrue")]))
        assert not r.ok
        assert "issues" in r.detail

    def test_repo_not_found(self):
        r = check_github("github.com", "org/nope", _runner([(1, "404")]))
        assert not r.ok
        assert "not found" in r.detail


class TestGitLab:
    def _project(self, issues=True, level=30):
        return json.dumps(
            {"issues_enabled": issues, "permissions": {"project_access": {"access_level": level}}}
        )

    def test_developer_access_ok(self):
        r = check_gitlab("workshop.cloud.gov", "g/p", _runner([(0, self._project())]))
        assert r.ok

    def test_below_developer_fails(self):
        r = check_gitlab("workshop.cloud.gov", "g/p", _runner([(0, self._project(level=20))]))
        assert r.ok  # visible; low/absent direct access reported, not hard-failed
        assert "visible" in r.detail

    def test_issues_disabled(self):
        r = check_gitlab("workshop.cloud.gov", "g/p", _runner([(0, self._project(issues=False))]))
        assert not r.ok

    def test_null_permissions_still_visible(self):
        payload = json.dumps({"issues_enabled": True, "permissions": {"project_access": None, "group_access": None}})
        r = check_gitlab("workshop.cloud.gov", "g/p", _runner([(0, payload)]))
        assert r.ok

    def test_project_not_found(self):
        r = check_gitlab("workshop.cloud.gov", "g/nope", _runner([(1, "404")]))
        assert not r.ok


class TestJira:
    def test_visible(self):
        r = check_jira("acli", "FPDF", _runner([(0, "[]")]))
        assert r.ok

    def test_not_visible(self):
        r = check_jira("acli", "NOPE", _runner([(1, "error")]))
        assert not r.ok


def test_preflight_uses_gitlab_project_config(mocker, monkeypatch, tmp_path):
    monkeypatch.delenv("GL_CG_REPO", raising=False)
    monkeypatch.delenv("CLOUDGOV_GLAB_HOST", raising=False)
    mocker.patch.object(cli, "_load_dotenv")
    mocker.patch.object(
        cli,
        "load_config",
        return_value={
            "gitlab": {"host": "gitlab.example", "project": "group/project"},
            "jira": {},
        },
    )
    check = mocker.patch.object(cli, "check_gitlab", return_value=type("Result", (), {"ok": True, "target": "gitlab.example", "resource": "group/project", "detail": "ok"})())

    cli.preflight(tmp_path / "omni-project.toml")

    check.assert_called_once_with("gitlab.example", "group/project")
