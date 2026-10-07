"""Structural diff engine for CanonicalIssue 3-way comparisons.

Comparisons strip the fed-sync-anchor footer before diffing bodies so that
provider-specific link metadata never shows up as a false-positive delta.
"""
from __future__ import annotations

from harness.models import CanonicalIssue, DiffResult, FieldDelta, strip_anchor

_COMPARED_FIELDS = ("title", "status", "priority", "labels", "assignees")


def compute_diff(left: CanonicalIssue, right: CanonicalIssue) -> DiffResult:
    """Compare two canonical issues field-by-field, returning all deltas."""
    deltas: list[FieldDelta] = []

    # Normalize CRLF -> LF before comparing: GitLab stores bodies LF-only, so a
    # CRLF-authored issue would otherwise show perpetual drift and oscillate on
    # every sync (see skills/omni-sync/known-failures.md #2).
    left_body = strip_anchor(left.body_markdown).replace("\r\n", "\n")
    right_body = strip_anchor(right.body_markdown).replace("\r\n", "\n")
    if left_body != right_body:
        deltas.append(FieldDelta("body_markdown", left_body, right_body))

    for name in _COMPARED_FIELDS:
        left_val = getattr(left, name)
        right_val = getattr(right, name)
        if isinstance(left_val, list):
            left_val, right_val = sorted(left_val), sorted(right_val)
        if left_val != right_val:
            deltas.append(FieldDelta(name, left_val, right_val))

    return DiffResult(deltas=deltas)
