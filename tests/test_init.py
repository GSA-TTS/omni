import tomllib

from typer.testing import CliRunner

from harness import cli

runner = CliRunner()


_PROJECT = [
    'jira.project_key="TEST"',
    'github.org="example-org"',
    'github.repos=["example-repo"]',
]


def test_init_generates_and_validates_all_config_files(tmp_path):
    result = runner.invoke(
        cli.app,
        [
            "init",
            "--directory",
            str(tmp_path),
            "--project",
            _PROJECT[0],
            "--project",
            _PROJECT[1],
            "--project",
            _PROJECT[2],
            "--user",
            'person@agency.gov.gh="login"',
            "--group",
            'team.members=["person@agency.gov"]',
        ],
    )
    assert result.exit_code == 0, result.output

    project = tomllib.loads((tmp_path / "omni-project.toml").read_text())
    users = tomllib.loads((tmp_path / "users.toml").read_text())
    assert project["github"]["repos"] == ["example-repo"]
    assert users["groups"]["team"]["members"] == ["person@agency.gov"]
    assert (tmp_path / ".env").exists()
    cli.validate(tmp_path / "omni-project.toml", tmp_path / "users.toml")


def test_init_validates_before_writing_any_file(tmp_path):
    result = runner.invoke(
        cli.app,
        [
            "init",
            "--directory",
            str(tmp_path),
            "--project",
            'github.org="missing-required-fields"',
        ],
    )
    assert result.exit_code == 1
    assert list(tmp_path.iterdir()) == []


def test_init_preserves_existing_files_without_force(tmp_path):
    project = tmp_path / "omni-project.toml"
    project.write_text("existing")
    result = runner.invoke(
        cli.app,
        [
            "init",
            "--directory",
            str(tmp_path),
            "--project",
            _PROJECT[0],
            "--project",
            _PROJECT[1],
            "--project",
            _PROJECT[2],
        ],
    )
    assert result.exit_code == 0, result.output
    assert project.read_text() == "existing"


def test_init_rejects_missing_directory(tmp_path):
    result = runner.invoke(
        cli.app,
        [
            "init",
            "--directory",
            str(tmp_path / "missing"),
            "--project",
            _PROJECT[0],
        ],
    )
    assert result.exit_code != 0
    assert "directory does not exist" in result.output


def test_init_removes_staged_files_when_first_replace_fails(mocker, tmp_path):
    replace = mocker.patch("pathlib.Path.replace", side_effect=OSError("disk error"))
    result = runner.invoke(
        cli.app,
        [
            "init",
            "--directory",
            str(tmp_path),
            "--project",
            _PROJECT[0],
            "--project",
            _PROJECT[1],
            "--project",
            _PROJECT[2],
        ],
    )
    assert result.exit_code == 1
    assert "failed to write configuration" in result.output
    assert replace.called
    assert list(tmp_path.iterdir()) == []


def test_init_accepts_migration_gate_flags(tmp_path):
    result = runner.invoke(
        cli.app,
        [
            "init",
            "--directory",
            str(tmp_path),
            "--github-org",
            "GSA-TTS",
            "--github-repo",
            "repo-one",
            "--github-repo",
            "repo-two",
            "--github-project-number",
            "101",
            "--jira-project-key",
            "FPDF",
            "--jira-base-url",
            "https://jira.example.gov",
            "--gitlab-host",
            "gitlab.example.gov",
            "--gitlab-project",
            "group/project",
            "--sync-labels",
            "--sync-assignee",
            "--sync-milestone",
            "--append-updates",
            "--label",
            "bug=bug",
            "--always-apply-jira-label",
            "github-sync",
        ],
    )

    assert result.exit_code == 0, result.output
    config = tomllib.loads((tmp_path / "omni-project.toml").read_text())
    assert config["github"]["repos"] == ["repo-one", "repo-two"]
    assert config["github"]["project_number"] == 101
    assert config["sync"]["sync_milestone"] is True
    assert config["labels"] == {"bug": "bug"}
    assert config["always_apply"]["jira_labels"] == ["github-sync"]


def test_init_repeat_requires_force(tmp_path):
    first = runner.invoke(
        cli.app,
        [
            "init",
            "--directory",
            str(tmp_path),
            "--project",
            _PROJECT[0],
            "--project",
            _PROJECT[1],
            "--project",
            _PROJECT[2],
        ],
    )
    assert first.exit_code == 0, first.output
    project = tmp_path / "omni-project.toml"
    original = project.read_text()

    second = runner.invoke(
        cli.app,
        [
            "init",
            "--directory",
            str(tmp_path),
            "--jira-project-key",
            "OTHER",
            "--github-org",
            "other-org",
            "--github-repo",
            "other-repo",
        ],
    )
    assert second.exit_code == 0
    assert project.read_text() == original

    forced = runner.invoke(
        cli.app,
        [
            "init",
            "--force",
            "--directory",
            str(tmp_path),
            "--jira-project-key",
            "OTHER",
            "--github-org",
            "other-org",
            "--github-repo",
            "other-repo",
        ],
    )
    assert forced.exit_code == 0, forced.output
    assert tomllib.loads(project.read_text())["jira"]["project_key"] == "OTHER"


def test_init_help_and_output_do_not_accept_secrets():
    result = runner.invoke(cli.app, ["init", "--help"])
    assert result.exit_code == 0
    assert "token" not in result.output.lower()
    assert "password" not in result.output.lower()
