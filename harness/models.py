"""Canonical data model shared by all provider adapters.

All issue-tracking providers (GitHub, GitLab, Jira) serialize to and from this
schema to avoid an M x N conversion matrix between provider formats.
"""
from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from typing import Literal

Status = Literal["OPEN", "CLOSED"]

ANCHOR_PREFIX = "fed-sync-anchor"
LINKS_PREFIX = "links"

_ANCHOR_RE = re.compile(
    rf"<!--\s*{ANCHOR_PREFIX}:\s*(?P<anchor>\S+)\s*-->"
    rf"\n?<!--\s*{LINKS_PREFIX}:\s*(?P<links>.*?)\s*-->\n?",
    re.MULTILINE,
)


@dataclass
class CanonicalIssue:
    """Normalized representation of an issue/ticket across all providers."""

    title: str
    body_markdown: str
    status: Status = "OPEN"
    priority: str | None = None
    labels: list[str] = field(default_factory=list)
    assignees: list[str] = field(default_factory=list)
    uuid: str = field(default_factory=lambda: f"urn:fed:sync:{uuid.uuid4().hex[:12]}")
    sync_metadata: dict[str, str] = field(default_factory=dict)

    @classmethod
    def create_new(cls, title: str, body_markdown: str, **kwargs) -> "CanonicalIssue":
        return cls(title=title, body_markdown=body_markdown, **kwargs)

    def body_with_anchor(self) -> str:
        """Return body markdown with the sync anchor footer appended."""
        clean_body = strip_anchor(self.body_markdown)
        if "\x00" in clean_body:
            raise ValueError("issue body contains a NUL byte, which no provider CLI accepts")
        links = " | ".join(f"{k}:{v}" for k, v in sorted(self.sync_metadata.items()))
        footer = f"<!-- {ANCHOR_PREFIX}: {self.uuid} -->\n<!-- {LINKS_PREFIX}: {links} -->"
        return f"{clean_body}\n\n{footer}" if clean_body else footer

    def diff(self, other: "CanonicalIssue") -> "DiffResult":
        from harness.engine.diff import compute_diff

        return compute_diff(self, other)


@dataclass(frozen=True)
class OpenIssue:
    """Read-only issue summary used by cross-provider reporting."""

    provider: str
    issue_id: str
    title: str
    body: str
    labels: tuple[str, ...]
    url: str


@dataclass(frozen=True)
class IssueQuery:
    """Provider-neutral filters for read-only issue reports."""

    relationships: tuple[str, ...] = ("authored", "assigned")
    users: tuple[str, ...] = ("@me",)
    state: str = "open"
    labels: tuple[str, ...] = ()
    search: str | None = None
    limit: int = 100


@dataclass
class FieldDelta:
    """A single detected difference between two canonical issues."""

    field: str
    left_val: object
    right_val: object


@dataclass
class DiffResult:
    """Collection of field-level deltas between two issues."""

    deltas: list[FieldDelta] = field(default_factory=list)

    @property
    def has_changes(self) -> bool:
        return len(self.deltas) > 0

    def render_table(self) -> str:
        if not self.has_changes:
            return "No differences found."
        lines = ["Field       | Left                           | Right", "-" * 70]
        for d in self.deltas:
            lines.append(f"{d.field:<12}| {str(d.left_val):<30} | {str(d.right_val)}")
        return "\n".join(lines)


def strip_anchor(body: str) -> str:
    """Remove the fed-sync-anchor and links metadata footer from a markdown body."""
    return _ANCHOR_RE.sub("", body or "").rstrip()


def parse_anchor(body: str) -> tuple[str | None, dict[str, str]]:
    """Extract the sync anchor UUID and link map from a markdown body, if present."""
    match = _ANCHOR_RE.search(body or "")
    if not match:
        return None, {}
    anchor = match.group("anchor")
    links: dict[str, str] = {}
    for pair in match.group("links").split("|"):
        pair = pair.strip()
        if ":" in pair:
            key, _, value = pair.partition(":")
            links[key.strip()] = value.strip()
    return anchor, links
