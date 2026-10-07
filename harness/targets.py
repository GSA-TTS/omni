"""Resolve configured provider targets with explicit environment overrides."""
from __future__ import annotations

import os
from collections.abc import Mapping


def resolve_gitlab_target(
    cfg: dict,
    environ: Mapping[str, str] | None = None,
) -> tuple[str, str | None]:
    """Return GitLab host/project; environment values override project config."""
    env = os.environ if environ is None else environ
    gitlab = cfg.get("gitlab", {})
    host = env.get("CLOUDGOV_GLAB_HOST") or gitlab.get("host") or "workshop.cloud.gov"
    project = env.get("GL_CG_REPO") or gitlab.get("project")
    return host, project
