"""Build validated TOML configuration from noninteractive CLI assignments."""

from __future__ import annotations

import json
import tomllib
from typing import Any

import tomli_w

from harness.config import validate_config
from harness.identity import _validate_users


def toml_assignment(path: str, value: Any) -> str:
    """Encode a Python value as one safe TOML assignment."""
    encoded = tomli_w.dumps({"value": value}).partition("=")[2].strip()
    return f"{path}={encoded}"


def map_assignment(table: str, key: str, value: Any) -> str:
    """Encode a potentially non-bare TOML map key and value."""
    return toml_assignment(f"{table}.{json.dumps(key)}", value)


def build_project_toml(assignments: list[str]) -> str:
    data: dict[str, Any] = {"schema_version": 1}
    for assignment in assignments:
        _merge(data, _parse_toml_assignment(assignment))
    validate_config(data)
    return tomli_w.dumps(data)


def build_users_toml(users: list[str], groups: list[str]) -> str:
    data: dict[str, Any] = {}
    for assignment in users:
        email, field, value = _parse_roster_assignment(assignment, "user")
        _assign(data, ("users", email, field), value)
    for assignment in groups:
        slug, field, value = _parse_roster_assignment(assignment, "group")
        _assign(data, ("groups", slug, field), value)
    _validate_users(data, None)
    return tomli_w.dumps(data)


def _parse_assignment(assignment: str) -> tuple[tuple[str, ...], Any]:
    key, separator, raw = assignment.partition("=")
    path = tuple(part.strip() for part in key.split("."))
    if not separator or not path or any(not part for part in path):
        raise ValueError(f"invalid assignment: {assignment!r}")
    try:
        value = tomllib.loads(f"value = {raw}")["value"]
    except tomllib.TOMLDecodeError as exc:
        raise ValueError(f"invalid TOML value for {key!r}: {exc}") from exc
    return path, value


def _parse_toml_assignment(assignment: str) -> dict[str, Any]:
    if "=" not in assignment:
        raise ValueError(f"invalid assignment: {assignment!r}")
    try:
        parsed = tomllib.loads(assignment)
    except tomllib.TOMLDecodeError as exc:
        raise ValueError(f"invalid TOML assignment {assignment!r}: {exc}") from exc
    if len(parsed) != 1:
        raise ValueError(f"assignment must set one top-level path: {assignment!r}")
    return parsed


def _parse_roster_assignment(assignment: str, kind: str) -> tuple[str, str, Any]:
    path, value = _parse_assignment(assignment)
    if len(path) < 2:
        raise ValueError(f"{kind} assignment must be ID.FIELD=VALUE")
    return ".".join(path[:-1]), path[-1], value


def _assign(data: dict[str, Any], path: tuple[str, ...], value: Any) -> None:
    current = data
    for part in path[:-1]:
        existing = current.setdefault(part, {})
        if not isinstance(existing, dict):
            raise ValueError(f"cannot assign beneath non-table field {part!r}")
        current = existing
    leaf = path[-1]
    if leaf in current:
        raise ValueError(f"duplicate assignment for {'.'.join(path)!r}")
    current[leaf] = value


def _merge(current: dict[str, Any], incoming: dict[str, Any], prefix: str = "") -> None:
    for key, value in incoming.items():
        path = f"{prefix}.{key}" if prefix else key
        if key not in current:
            current[key] = value
        elif isinstance(current[key], dict) and isinstance(value, dict):
            _merge(current[key], value, path)
        else:
            raise ValueError(f"duplicate assignment for {path!r}")
