from harness import cli
from harness.workspace import config_path, find_workspace


def test_project_file_is_the_only_workspace_marker(tmp_path):
    project = tmp_path / "project"
    nested = project / "nested"
    nested.mkdir(parents=True)
    (nested / ".env").write_text("SHADOW=true\n")
    (nested / "users.toml").write_text("[users]\n")
    (project / "omni-project.toml").write_text("schema_version = 1\n")

    assert find_workspace(nested) == project
    assert config_path("users.toml", find_workspace(nested)) == project / "users.toml"


def test_workspace_falls_back_to_start_for_init(tmp_path):
    assert find_workspace(tmp_path) == tmp_path


def test_runtime_config_resolves_after_changing_directory(tmp_path, monkeypatch):
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    (first / "omni-project.toml").touch()
    (second / "omni-project.toml").touch()

    monkeypatch.chdir(first)
    assert cli._runtime_config() == first / "omni-project.toml"
    monkeypatch.chdir(second)
    assert cli._runtime_config() == second / "omni-project.toml"


def test_explicit_config_controls_sibling_local_files(tmp_path, monkeypatch):
    config = tmp_path / "workspace" / "omni-project.toml"
    config.parent.mkdir()
    config.touch()
    (config.parent / ".env").write_text("OMNI_WORKSPACE_TEST=from-config\n")
    monkeypatch.delenv("OMNI_WORKSPACE_TEST", raising=False)

    resolved = cli._runtime_config(config)
    cli._load_dotenv(resolved.parent / ".env")

    assert resolved == config
    assert cli.os.environ["OMNI_WORKSPACE_TEST"] == "from-config"
