from harness.targets import resolve_gitlab_target


def test_gitlab_target_uses_project_config():
    cfg = {"gitlab": {"host": "gitlab.example", "project": "group/project"}}
    assert resolve_gitlab_target(cfg, {}) == ("gitlab.example", "group/project")


def test_gitlab_target_environment_overrides_project_config():
    cfg = {"gitlab": {"host": "configured.example", "project": "configured/project"}}
    env = {"CLOUDGOV_GLAB_HOST": "override.example", "GL_CG_REPO": "override/project"}
    assert resolve_gitlab_target(cfg, env) == ("override.example", "override/project")


def test_gitlab_target_has_safe_host_default():
    assert resolve_gitlab_target({}, {}) == ("workshop.cloud.gov", None)
