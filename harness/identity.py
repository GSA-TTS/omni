"""Cross-host identity map keyed on email (the pivot field).

Loads identity_map.toml -- a table per host base URL, each row mapping an
email to that host's username. Lets the harness translate the same person's
assignee between GitHub.com, GitHub Enterprise Server (Helix), and GitLab
(cloud.gov) without a per-pair mapping.
"""
from __future__ import annotations

import tomllib
from pathlib import Path

# Logical target name -> host base URL as written in identity_map.toml.
HOST_URLS = {
    "gh-tts": "https://github.com/GSA-TTS",
    "gh-helix": "https://github.helix.gsa.gov/",
    "gl-cg": "https://workshop.cloud.gov/",
}


class IdentityMap:
    """Email-pivoted username lookups across provider hosts."""

    def __init__(self, by_host: dict[str, dict[str, str]]):
        # by_host[host_url][email_lower] = username
        self._by_host = {
            host: {e.lower(): u for e, u in rows.items()} for host, rows in by_host.items()
        }

    @classmethod
    def load(cls, path: Path) -> "IdentityMap":
        if not path.exists():
            return cls({})
        return cls(tomllib.loads(path.read_text()))

    def username(self, host_url: str, email: str) -> str | None:
        """Username for an email on a given host URL, or None."""
        return self._by_host.get(host_url, {}).get(email.lower())

    def username_for_target(self, target: str, email: str) -> str | None:
        """Username for an email on a logical target (gh-tts/gh-helix/gl-cg)."""
        host_url = HOST_URLS.get(target)
        return self.username(host_url, email) if host_url else None

    def email_for_username(self, host_url: str, username: str) -> str | None:
        """Reverse lookup: the email mapped to a username on a host, or None."""
        for email, user in self._by_host.get(host_url, {}).items():
            if user.lower() == username.lower():
                return email
        return None

    def translate(self, from_host: str, to_host: str, username: str) -> str | None:
        """Map a username on one host to the same person's username on another."""
        email = self.email_for_username(from_host, username)
        return self.username(to_host, email) if email else None

    def resolve_assignee(self, target: str, value: str) -> str | None:
        """Resolve an assignee for a target from an email or a username.

        If `value` is an email with a mapping for the target, return that
        host's username. Otherwise return the value unchanged (already a
        username, or an email with no mapping -- callers decide whether to
        proceed). Returns None only when an email has no mapping on the host.
        """
        if "@" in value:
            return self.username_for_target(target, value)
        return value

