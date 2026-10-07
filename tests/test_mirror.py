import subprocess

from harness.engine.mirror import GitMirror


def _ok(stdout: str = "") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=[], returncode=0, stdout=stdout, stderr="")


def _fail(stderr: str = "boom") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr=stderr)


_REMOTES = {
    "origin": "git@github.com:GSA-TTS/omni.git",
    "helix": "git@github.helix.gsa.gov:example-owner/omni.git",
}


def test_dry_run_pushes_nothing(mocker):
    run_mock = mocker.patch("subprocess.run")
    results = GitMirror(_REMOTES).push("main", ["origin", "helix"], dry_run=True)

    run_mock.assert_not_called()
    assert all(r.ok for r in results)
    assert all(r.message.startswith("dry-run:") for r in results)


def test_unknown_target_reported_not_fatal(mocker):
    mocker.patch(
        "subprocess.run", return_value=_ok("to github\n * [new branch] main -> main")
    )
    results = GitMirror(_REMOTES).push("main", ["origin", "nope"], dry_run=False)

    by_name = {r.remote: r for r in results}
    assert by_name["origin"].ok is True
    assert by_name["nope"].ok is False
    assert "no remote" in by_name["nope"].message


def test_adds_remote_when_absent_then_pushes(mocker):
    # get-url fails (absent) -> remote add -> push ok
    run_mock = mocker.patch(
        "subprocess.run",
        side_effect=[_fail("no such remote"), _ok(), _ok("Everything up-to-date")],
    )
    results = GitMirror({"helix": _REMOTES["helix"]}).push(
        "main", ["helix"], dry_run=False
    )

    assert results[0].ok
    cmds = [call.args[0] for call in run_mock.call_args_list]
    assert ["git", "remote", "get-url", "helix"] in cmds
    assert any(c[:3] == ["git", "remote", "add"] for c in cmds)
    assert cmds[-1] == ["git", "push", "helix", "main"]


def test_updates_remote_url_when_present(mocker):
    # get-url ok (present) -> set-url -> push ok
    run_mock = mocker.patch(
        "subprocess.run",
        side_effect=[_ok("old-url"), _ok(), _ok("pushed")],
    )
    GitMirror({"origin": _REMOTES["origin"]}).push("main", ["origin"], dry_run=False)

    cmds = [call.args[0] for call in run_mock.call_args_list]
    assert any(c[:3] == ["git", "remote", "set-url"] for c in cmds)


def test_push_failure_reported(mocker):
    mocker.patch("subprocess.run", side_effect=[_ok("url"), _ok(), _fail("rejected")])
    results = GitMirror({"origin": _REMOTES["origin"]}).push(
        "main", ["origin"], dry_run=False
    )

    assert results[0].ok is False
    assert "rejected" in results[0].message


def test_default_does_not_force_ssh_batchmode(mocker):
    """Interactive auth (SSH passphrase / gh web session) must not be suppressed by default."""
    run_mock = mocker.patch(
        "subprocess.run", side_effect=[_ok("url"), _ok(), _ok("pushed")]
    )
    GitMirror({"origin": _REMOTES["origin"]}).push("main", ["origin"], dry_run=False)
    env = run_mock.call_args_list[-1].kwargs["env"]
    assert "GIT_SSH_COMMAND" not in env or "BatchMode" not in env["GIT_SSH_COMMAND"]


def test_batch_opt_in_sets_ssh_batchmode(mocker):
    run_mock = mocker.patch(
        "subprocess.run", side_effect=[_ok("url"), _ok(), _ok("pushed")]
    )
    GitMirror({"origin": _REMOTES["origin"]}, batch=True).push(
        "main", ["origin"], dry_run=False
    )
    env = run_mock.call_args_list[-1].kwargs["env"]
    assert "BatchMode=yes" in env["GIT_SSH_COMMAND"]
