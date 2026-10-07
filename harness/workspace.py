"""Locate omni-sync config files relative to where the CLI is run.

The CLI may be invoked from any directory. Config is discovered by walking up
from the current working directory looking for the committed
``omni-project.toml`` marker, falling back to the CWD for a fresh ``init``.
"""

from __future__ import annotations

from pathlib import Path

WORKSPACE_MARKER = "omni-project.toml"

# Files whose absence should warn (the ones holding real, local-only data).
LOCAL_ONLY = ("users.toml", ".env")


def find_workspace(start: Path | None = None) -> Path:
    """Return the directory holding omni-sync config, searching CWD upward.

    Picks the nearest ancestor containing WORKSPACE_MARKER; if none is found,
    returns the starting directory (so a fresh `init` lands in the CWD).
    """
    start = (start or Path.cwd()).resolve()
    for directory in (start, *start.parents):
        if (directory / WORKSPACE_MARKER).is_file():
            return directory
    return start


def config_path(name: str, workspace: Path | None = None) -> Path:
    """Absolute path to a named config file within the resolved workspace."""
    return (workspace or find_workspace()) / name


def missing_local_files(workspace: Path | None = None) -> list[str]:
    """Return the LOCAL_ONLY files absent from the workspace."""
    ws = workspace or find_workspace()
    return [name for name in LOCAL_ONLY if not (ws / name).exists()]


def template_name(name: str) -> str:
    """Packaged resource name for a local config file."""
    return ".env.example" if name == ".env" else f"{name}.example"
