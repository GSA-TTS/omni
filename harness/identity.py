"""Team roster, keyed on email (the pivot field).

Loads the `[users."<email>"]` tables from users.toml (the single PII file;
gitignored). Each entry lists a person's username per host, from which the
harness derives:
  * --assignee <email> -> that host's username (create / pr)
  * GitHub login -> Jira email (the gh-jira sync assignee translation)

Host field names map to logical targets: gh (github.com), helix (GHES),
gitlab (workshop.cloud.gov). Jira assignees use the email key directly.
"""
from __future__ import annotations

import tomllib
from pathlib import Path

# Logical target name -> the per-user field holding that host's username.
TARGET_FIELD = {
    "gh-tts": "gh",
    "gh-helix": "helix",
    "gl-cg": "gitlab",
}

# Default location of the single roster file.
USERS_TOML = Path(__file__).resolve().parent.parent / "users.toml"
_SCHEMA_PATH = Path(__file__).resolve().parent.parent / "schema" / "users.schema.json"


class UserRoster:
    """Email-pivoted lookups over the users roster."""

    def __init__(self, users: dict[str, dict]):
        # users["email"] = {gh, helix, gitlab}; lower-case the email keys.
        self._by_email = {email.lower(): entry for email, entry in users.items()}

    @classmethod
    def load(cls, path: Path = USERS_TOML, validate: bool = True) -> "UserRoster":
        if not path.exists():
            return cls({})
        data = tomllib.loads(path.read_text())
        if validate:
            _validate_users(data, path)
        return cls(data.get("users", {}))

    def username_for_target(self, target: str, email: str) -> str | None:
        """Username for an email on a logical target (gh-tts/gh-helix/gl-cg)."""
        field = TARGET_FIELD.get(target)
        if not field:
            return None
        entry = self._by_email.get(email.lower())
        return entry.get(field) if entry else None

    def email_for_username(self, target: str, username: str) -> str | None:
        """Reverse lookup: the email whose target-host username matches, or None."""
        field = TARGET_FIELD.get(target)
        if not field:
            return None
        for email, entry in self._by_email.items():
            if (entry.get(field) or "").lower() == username.lower():
                return email
        return None

    def translate(self, from_target: str, to_target: str, username: str) -> str | None:
        """Map a username on one target to the same person's username on another."""
        email = self.email_for_username(from_target, username)
        return self.username_for_target(to_target, email) if email else None

    def resolve_assignee(self, target: str, value: str) -> str | None:
        """Resolve an assignee for a target from an email or a username.

        An email with a roster entry becomes that host's username. A plain
        username passes through unchanged. Returns None only when an email has
        no username for that host.
        """
        if "@" in value:
            return self.username_for_target(target, value)
        return value

    def github_login_to_jira_email(self) -> dict[str, str]:
        """Map every known GitHub login (github.com or Helix) -> Jira email.

        Used by the gh-jira sync to translate a GitHub assignee to a Jira user.
        """
        out: dict[str, str] = {}
        for email, entry in self._by_email.items():
            for field in ("gh", "helix"):
                login = entry.get(field)
                if login:
                    out[login.lower()] = email
        return out


def _validate_users(data: dict, source: Path) -> None:
    """Validate users.toml against schema/users.schema.json if jsonschema is present.

    Falls back to a minimal structural check otherwise. Exits on failure so a
    malformed roster surfaces before any assignee resolution.
    """
    import json
    import sys

    try:
        import jsonschema  # type: ignore
    except ImportError:
        users = data.get("users", {})
        if not isinstance(users, dict):
            sys.exit(f"users.toml invalid in {source}: [users] must be a table")
        return

    schema = json.loads(_SCHEMA_PATH.read_text())
    try:
        jsonschema.validate(data, schema)
    except jsonschema.ValidationError as exc:  # pragma: no cover - exercised when installed
        sys.exit(f"users.toml invalid in {source}: {exc.message}")

    users = {email.lower() for email in data.get("users", {})}
    for group, entry in data.get("groups", {}).items():
        unknown = sorted(email for email in entry["members"] if email.lower() not in users)
        if unknown:
            sys.exit(
                f"users.toml invalid in {source}: group {group!r} references unknown users: "
                f"{', '.join(unknown)}"
            )
