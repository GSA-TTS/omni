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

    left_body = strip_anchor(left.body_markdown)
    right_body = strip_anchor(right.body_markdown)
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
