from harness import cli
from harness.adapters.gitlab import GitLabAdapter


def test_resolve_gitlab_adapter_uses_project_config(mocker, monkeypatch, tmp_path):
    monkeypatch.delenv("GL_CG_REPO", raising=False)
    monkeypatch.delenv("CLOUDGOV_GLAB_HOST", raising=False)
    mocker.patch.object(cli, "_load_dotenv")
    mocker.patch.object(
        cli, "_runtime_config", return_value=tmp_path / "omni-project.toml"
    )
    mocker.patch.object(
        cli,
        "load_config",
        return_value={"gitlab": {"host": "gitlab.example", "project": "group/project"}},
    )

    adapter = cli._resolve_adapter("gl-cg")

    assert isinstance(adapter, GitLabAdapter)
    assert adapter.host == "gitlab.example"
    assert adapter.repo == "group/project"


def test_resolve_gitlab_adapter_environment_overrides_config(
    mocker, monkeypatch, tmp_path
):
    monkeypatch.setenv("GL_CG_REPO", "override/project")
    monkeypatch.setenv("CLOUDGOV_GLAB_HOST", "override.example")
    mocker.patch.object(cli, "_load_dotenv")
    mocker.patch.object(
        cli, "_runtime_config", return_value=tmp_path / "omni-project.toml"
    )
    mocker.patch.object(
        cli,
        "load_config",
        return_value={
            "gitlab": {"host": "configured.example", "project": "configured/project"}
        },
    )

    adapter = cli._resolve_adapter("gl-cg")

    assert adapter.host == "override.example"
    assert adapter.repo == "override/project"
