"""Load and validate the single omni-project.toml configuration.

Tables: [jira], [github], [mirror], [sync], [labels], [always_apply], plus a
top-level `schema_version`. The committed omni-project.toml is PII-free; the
developer roster (GitHub login -> Jira email) is derived from the gitignored
users.toml. All string lookups are case-insensitive.

Validated against schema/omni-project.schema.json when the (optional)
`jsonschema` package is available; otherwise a minimal built-in check runs.
"""

from __future__ import annotations

import json
import re
import sys
import tomllib
from pathlib import Path
from typing import Any

from harness.resources import resource_text

_LABEL_UNSAFE_RE = re.compile(r"\s+")

_SUPPORTED_SCHEMA_VERSION = 1


class ConfigError(RuntimeError):
    """Raised when omni-project.toml is missing or fails validation."""


def load_config(path: Path) -> dict[str, Any]:
    """Parse omni-project.toml, validate it, and merge the gitignored roster.

    * The committed omni-project.toml carries [jira]/[github]/[mirror]/[sync]/
      [labels]/[always_apply] and a `schema_version`.
    * users.toml (gitignored) supplies the team roster; the [developers] map
      (GitHub login -> Jira email) is DERIVED from it.
    """
    if not path.exists():
        sys.exit(f"omni-project.toml not found at {path}")
    cfg = tomllib.loads(path.read_text())
    validate_config(cfg, source=path)

    users_path = path.parent / "users.toml"
    if users_path.exists():
        users = tomllib.loads(users_path.read_text()).get("users", {})
        cfg["developers"] = _developers_from_users(users)

    return cfg


def validate_config(cfg: dict, source: Path | None = None) -> None:
    """Validate cfg against the JSON schema (jsonschema if present, else minimal).

    Exits the process with a clear message on failure, so the CLI fails fast
    instead of mutating remote systems from a malformed config.
    """
    version = cfg.get("schema_version")
    if version != _SUPPORTED_SCHEMA_VERSION:
        where = f" in {source}" if source else ""
        sys.exit(
            f"omni-project.toml schema_version={version!r}{where} is unsupported; "
            f"this build expects {_SUPPORTED_SCHEMA_VERSION}"
        )

    _validate_supported_settings(cfg, source)

    try:
        import jsonschema  # type: ignore
    except ImportError:
        _minimal_validate(cfg, source)
        return

    schema = json.loads(resource_text("schema/omni-project.schema.json"))
    try:
        jsonschema.validate(cfg, schema)
    except (
        jsonschema.ValidationError
    ) as exc:  # pragma: no cover - exercised when installed
        where = f" in {source}" if source else ""
        sys.exit(f"omni-project.toml invalid{where}: {exc.message}")


def _minimal_validate(cfg: dict, source: Path | None) -> None:
    """Dependency-free structural check covering the required fields."""
    where = f" in {source}" if source else ""
    if not isinstance(cfg.get("jira"), dict) or not cfg["jira"].get("project_key"):
        sys.exit(f"omni-project.toml{where}: [jira].project_key is required")
    github = cfg.get("github")
    if not isinstance(github, dict) or not github.get("org"):
        sys.exit(f"omni-project.toml{where}: [github].org is required")
    repos = github.get("repos")
    if not isinstance(repos, list) or not repos:
        sys.exit(f"omni-project.toml{where}: [github].repos must be a non-empty list")


def _validate_supported_settings(cfg: dict, source: Path | None) -> None:
    """Reject enabled settings that this build cannot safely execute."""
    if cfg.get("sync", {}).get("sync_status") is True:
        where = f" in {source}" if source else ""
        sys.exit(
            f"omni-project.toml invalid{where}: [sync].sync_status=true is unsupported; "
            "Jira status transitions require workflow-specific mappings"
        )


def _developers_from_users(users: dict[str, dict]) -> dict[str, str]:
    """Derive a GitHub login -> Jira email map from the users roster.

    Roster is keyed by email: `[users."<email>"]` with gh/helix/gitlab fields.
    Both github.com (`gh`) and Helix (`helix`) logins point at the same email.
    """
    out: dict[str, str] = {}
    for email, entry in users.items():
        if not isinstance(entry, dict):
            continue
        for field in ("gh", "helix"):
            login = entry.get(field)
            if login:
                out[login] = email
    return out


def sanitize_jira_label(name: str) -> str:
    """Jira labels cannot contain spaces -- replace runs of whitespace with hyphens."""
    return _LABEL_UNSAFE_RE.sub("-", name.strip())


def lookup_ci(mapping: dict[str, str], key: str) -> str | None:
    """Case-insensitive lookup on a small dict."""
    if not key:
        return None
    if key in mapping:
        return mapping[key]
    lo = key.lower()
    for existing_key, value in mapping.items():
        if existing_key.lower() == lo:
            return value
    return None


def map_labels(gh_labels: list[str], cfg: dict) -> list[str]:
    """Translate GitHub labels to Jira labels via the [labels] map.

    Unlisted labels pass through sanitized. The [always_apply] labels are
    appended for traceability.
    """
    label_map: dict[str, str] = cfg.get("labels", {})
    out: list[str] = []
    for label in gh_labels:
        mapped = lookup_ci(label_map, label)
        out.append(sanitize_jira_label(mapped if mapped is not None else label))
    always = cfg.get("always_apply", {}).get("jira_labels", []) or []
    out.extend(sanitize_jira_label(x) for x in always)
    return sorted({x for x in out if x})


def map_assignee(gh_assignees: list[str], cfg: dict) -> str | None:
    """Translate the first mappable GitHub login to a Jira assignee email."""
    if not gh_assignees:
        return None
    dev_map: dict[str, str] = cfg.get("developers", {})
    for login in gh_assignees:
        email = lookup_ci(dev_map, login)
        if email:
            return email
    return None


def email_to_login_map(cfg: dict) -> dict[str, str]:
    """Invert [developers] (GitHub login -> Jira email) for reverse lookup."""
    dev_map: dict[str, str] = cfg.get("developers", {})
    return {email.lower(): login for login, email in dev_map.items()}


def milestone_label(gh_milestone: str | None, cfg: dict) -> str | None:
    """Encode a GitHub milestone as a prefixed Jira label (acli has no sprint flag)."""
    if not gh_milestone:
        return None
    prefix = cfg["sync"].get("milestone_label_prefix", "milestone:")
    return sanitize_jira_label(f"{prefix}{gh_milestone}")
