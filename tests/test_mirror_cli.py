import pytest
import typer

from harness import cli
from harness.engine.mirror import MirrorResult


def test_mirror_uses_inline_remote_without_project_config(mocker, tmp_path):
    (tmp_path / ".git").mkdir()
    load = mocker.patch.object(cli, "load_config")
    push = mocker.patch.object(
        cli.GitMirror,
        "push",
        return_value=[MirrorResult("helix", "ssh://helix/repo", True, "ok")],
    )

    cli.mirror(
        "HEAD",
        "review/source",
        ["helix"],
        ["helix=ssh://helix/repo"],
        tmp_path,
        None,
        True,
        True,
        False,
        False,
    )

    load.assert_not_called()
    push.assert_called_once_with(
        "HEAD",
        "review/source",
        ["helix"],
        dry_run=True,
        allow_non_head=False,
        allow_existing=False,
    )


def test_inline_remote_overrides_project_config(mocker, tmp_path):
    (tmp_path / ".git").mkdir()
    config = tmp_path / "omni-project.toml"
    config.touch()
    mocker.patch.object(
        cli,
        "load_config",
        return_value={"mirror": {"helix": "ssh://old/repo"}},
    )
    constructor = mocker.patch.object(cli, "GitMirror", autospec=True)
    constructor.return_value.push.return_value = []

    cli.mirror(
        "HEAD",
        "main",
        [],
        ["helix=ssh://new/repo"],
        tmp_path,
        config,
        True,
        False,
        False,
        False,
    )

    constructor.assert_called_once_with(
        {"helix": "ssh://new/repo"}, cwd=str(tmp_path), batch=False
    )


def test_mirror_rejects_non_repository(tmp_path):
    with pytest.raises(typer.BadParameter, match="not a Git repository"):
        cli.mirror(
            "HEAD",
            "main",
            [],
            ["x=ssh://host/repo"],
            tmp_path,
            None,
            True,
            False,
            False,
            False,
        )


def test_mirror_rejects_invalid_inline_remote(tmp_path):
    (tmp_path / ".git").mkdir()
    with pytest.raises(typer.BadParameter, match="NAME=URL"):
        cli.mirror(
            "HEAD", "main", [], ["invalid"], tmp_path, None, True, False, False, False
        )


def test_mirror_dry_run_exits_nonzero_on_safety_failure(mocker, tmp_path):
    (tmp_path / ".git").mkdir()
    mocker.patch.object(
        cli.GitMirror,
        "push",
        return_value=[MirrorResult("helix", "ssh://helix/repo", False, "blocked")],
    )

    with pytest.raises(typer.Exit) as raised:
        cli.mirror(
            "HEAD",
            "main",
            ["helix"],
            ["helix=ssh://helix/repo"],
            tmp_path,
            None,
            True,
            False,
            False,
            False,
        )

    assert raised.value.exit_code == 1
