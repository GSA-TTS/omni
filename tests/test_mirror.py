import subprocess

from harness.engine.mirror import GitMirror


def _ok(stdout: str = "") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=[], returncode=0, stdout=stdout, stderr="")


def _fail(stderr: str = "boom") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr=stderr)


_URL = "git@github.helix.gsa.gov:org/repo.git"
_SHA = "a" * 40
_OLD = "b" * 40


def _source_checks(remote_output: str = ""):
    return [_ok(), _ok(_SHA), _ok(_SHA), _ok(), _ok(remote_output)]


def test_dry_run_resolves_head_to_explicit_sha_refspec(mocker):
    run = mocker.patch("subprocess.run", side_effect=_source_checks())
    result = GitMirror({"helix": _URL}).push("HEAD", "main", ["helix"], dry_run=True)[0]

    assert result.ok
    assert f"{_SHA}:refs/heads/main" in result.message
    assert "new branch" in result.message
    commands = [call.args[0] for call in run.call_args_list]
    assert [
        "git",
        "rev-parse",
        "--verify",
        "--end-of-options",
        "HEAD^{commit}",
    ] in commands
    assert not any(command[:2] == ["git", "push"] for command in commands)


def test_stale_branch_is_rejected_when_not_checked_out(mocker):
    mocker.patch("subprocess.run", side_effect=[_ok(), _ok(_OLD), _ok(_SHA)])
    result = GitMirror({"helix": _URL}).push("main", "main", ["helix"], dry_run=True)[0]

    assert not result.ok
    assert "checked-out HEAD" in result.message
    assert "--allow-non-head" in result.message


def test_allow_non_head_pushes_exact_historical_sha(mocker):
    run = mocker.patch(
        "subprocess.run",
        side_effect=[_ok(), _ok(_OLD), _ok(_SHA), _ok(), _ok(), _ok("pushed")],
    )
    result = GitMirror({"archive": _URL}).push(
        "main",
        "archive/main",
        ["archive"],
        dry_run=False,
        allow_non_head=True,
    )[0]

    assert result.ok
    assert run.call_args_list[-1].args[0] == [
        "git",
        "push",
        "--",
        _URL,
        f"{_OLD}:refs/heads/archive/main",
    ]


def test_existing_destination_is_rejected_by_default(mocker):
    mocker.patch(
        "subprocess.run",
        side_effect=_source_checks(f"{_OLD}\trefs/heads/main\n"),
    )
    result = GitMirror({"workshop": _URL}).push(
        "HEAD", "main", ["workshop"], dry_run=True
    )[0]

    assert not result.ok
    assert "already exists" in result.message
    assert "review branch" in result.message


def test_identical_destination_is_idempotent_success(mocker):
    run = mocker.patch(
        "subprocess.run",
        side_effect=_source_checks(f"{_SHA}\trefs/heads/main\n"),
    )
    result = GitMirror({"helix": _URL}).push("HEAD", "main", ["helix"], dry_run=False)[
        0
    ]

    assert result.ok
    assert "already synchronized" in result.message
    assert not any(call.args[0][1] == "push" for call in run.call_args_list)


def test_embedded_https_credentials_are_rejected_before_remote_access(mocker):
    run = mocker.patch(
        "subprocess.run", side_effect=[_ok(), _ok(_SHA), _ok(_SHA), _ok()]
    )
    result = GitMirror({"unsafe": "https://token@example.test/repo.git"}).push(
        "HEAD", "main", ["unsafe"], dry_run=True
    )[0]

    assert not result.ok
    assert result.url == ""
    assert "embedded credentials" in result.message
    assert not any(call.args[0][1] == "ls-remote" for call in run.call_args_list)


def test_ssh_username_without_password_is_allowed(mocker):
    url = "ssh://git@example.test/org/repo.git"
    mocker.patch("subprocess.run", side_effect=_source_checks())
    result = GitMirror({"ssh": url}).push("HEAD", "main", ["ssh"], dry_run=True)[0]
    assert result.ok


def test_allow_existing_reports_both_shas_before_apply(mocker):
    run = mocker.patch(
        "subprocess.run",
        side_effect=[
            *_source_checks(f"{_OLD}\trefs/heads/main\n"),
            _ok("fast-forwarded"),
        ],
    )
    result = GitMirror({"helix": _URL}).push(
        "HEAD",
        "main",
        ["helix"],
        dry_run=False,
        allow_existing=True,
    )[0]

    assert result.ok
    assert run.call_args_list[-1].args[0] == [
        "git",
        "push",
        "--",
        _URL,
        f"{_SHA}:refs/heads/main",
    ]


def test_integrity_failure_blocks_all_targets(mocker):
    mocker.patch(
        "subprocess.run",
        side_effect=[_ok(), _ok(_SHA), _ok(_SHA), _fail("bad object")],
    )
    results = GitMirror({"one": _URL, "two": _URL}).push("HEAD", "main", ["one", "two"])

    assert all(not result.ok for result in results)
    assert all("object-integrity" in result.message for result in results)


def test_unknown_target_is_reported_without_push(mocker):
    run = mocker.patch(
        "subprocess.run", side_effect=[_ok(), _ok(_SHA), _ok(_SHA), _ok()]
    )
    result = GitMirror({"helix": _URL}).push(
        "HEAD", "main", ["unknown"], dry_run=False
    )[0]
    assert not result.ok
    assert "no remote" in result.message
    assert not any(call.args[0][:2] == ["git", "push"] for call in run.call_args_list)


def test_batch_mode_is_applied_to_remote_probes_and_push(mocker):
    run = mocker.patch("subprocess.run", side_effect=[*_source_checks(), _ok("pushed")])
    GitMirror({"helix": _URL}, batch=True).push(
        "HEAD", "main", ["helix"], dry_run=False
    )
    remote_calls = [
        call for call in run.call_args_list if call.args[0][1] in {"ls-remote", "push"}
    ]
    assert remote_calls
    assert all(
        "BatchMode=yes" in call.kwargs["env"]["GIT_SSH_COMMAND"]
        for call in remote_calls
    )


def test_invalid_destination_is_rejected_before_source_resolution(mocker):
    run = mocker.patch("subprocess.run", return_value=_fail("invalid"))
    result = GitMirror({"helix": _URL}).push(
        "HEAD", "-invalid", ["helix"], dry_run=True
    )[0]
    assert not result.ok
    assert "invalid destination" in result.message
    assert run.call_count == 1
