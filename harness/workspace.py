"""Locate omni-sync config files relative to where the CLI is run.

The CLI may be invoked from any directory. Config is discovered by walking up
from the current working directory looking for an "omni marker" (any of the
known config files), falling back to the CWD. This lets a team keep their
committed omni-project.toml and gitignored users.toml / .env beside their
checkout rather than inside the installed package.
"""
from __future__ import annotations

from pathlib import Path

# Config file names the workspace is expected to contain.
CONFIG_FILES = ("omni-project.toml", "users.toml", ".env")

# Files whose absence should warn (the ones holding real, local-only data).
LOCAL_ONLY = ("users.toml", ".env")

# Packaged templates shipped in the repo root, used by `init`.
_PACKAGE_ROOT = Path(__file__).resolve().parent.parent


def find_workspace(start: Path | None = None) -> Path:
    """Return the directory holding omni-sync config, searching CWD upward.

    Picks the nearest ancestor containing any CONFIG_FILES; if none is found,
    returns the starting directory (so a fresh `init` lands in the CWD).
    """
    start = (start or Path.cwd()).resolve()
    for directory in (start, *start.parents):
        if any((directory / name).exists() for name in CONFIG_FILES):
            return directory
    return start


def config_path(name: str, workspace: Path | None = None) -> Path:
    """Absolute path to a named config file within the resolved workspace."""
    return (workspace or find_workspace()) / name


def missing_local_files(workspace: Path | None = None) -> list[str]:
    """Return the LOCAL_ONLY files absent from the workspace."""
    ws = workspace or find_workspace()
    return [name for name in LOCAL_ONLY if not (ws / name).exists()]


def template_for(name: str) -> Path:
    """Path to the committed *.example (or base) template for a config file."""
    if name == ".env":
        return _PACKAGE_ROOT / ".env.example"
    example = _PACKAGE_ROOT / f"{name}.example"
    return example if example.exists() else _PACKAGE_ROOT / name
