"""Load and interpret the TOML sync config shared by the GitHub<->Jira engine.

Transposed from the proven TTSE petrified-forest `sync_config.toml` schema.
Keeps the same tables: [jira], [github], [sync], [developers], [labels],
[always_apply]. All string lookups are case-insensitive.
"""
from __future__ import annotations

import re
import sys
import tomllib
from pathlib import Path
from typing import Any

_LABEL_UNSAFE_RE = re.compile(r"\s+")


def load_config(path: Path) -> dict[str, Any]:
    """Parse a sync_config.toml file into a dict, exiting on a missing file."""
    if not path.exists():
        sys.exit(f"sync_config.toml not found at {path}")
    return tomllib.loads(path.read_text())


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
