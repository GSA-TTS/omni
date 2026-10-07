"""Strip or inject the fed-sync-anchor metadata footer from issue bodies.

Kept separate from models.py's low-level regex helpers so adapters can apply
provider-specific sanitization (e.g. stripping Jira ADF panel wrappers) without
touching the canonical model.
"""
from __future__ import annotations

from harness.models import parse_anchor, strip_anchor

__all__ = ["strip_anchor", "parse_anchor", "strip_html_comments"]


def strip_html_comments(body: str) -> str:
    """Remove all HTML comments from a markdown body, not just sync anchors."""
    import re

    return re.sub(r"<!--.*?-->\n?", "", body or "", flags=re.DOTALL).rstrip()
