"""Structural diff engine for CanonicalIssue 3-way comparisons.

Comparisons strip the fed-sync-anchor footer before diffing bodies so that
provider-specific link metadata never shows up as a false-positive delta.
"""
from __future__ import annotations

from typing import Literal

from harness.models import CanonicalIssue, DiffResult, FieldDelta, strip_anchor

LabelMode = Literal["exact", "additive"]
LabelSource = Literal["left", "right"]

_COMPARED_FIELDS = ("title", "status", "priority", "assignees")


def compute_diff(
    left: CanonicalIssue,
    right: CanonicalIssue,
    *,
    label_mode: LabelMode = "exact",
    label_source: LabelSource = "left",
) -> DiffResult:
    """Compare two canonical issues field-by-field, returning all deltas.

    ``label_mode="exact"`` treats label sets as fully authoritative and reports
    any mismatch. ``label_mode="additive"`` is directional: it only reports
    labels that are missing from the target side, matching provider adapters
    that can safely add labels but do not remove target-only labels.
    """
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

    left_labels = sorted(left.labels)
    right_labels = sorted(right.labels)
    if label_mode == "exact":
        if left_labels != right_labels:
            deltas.append(FieldDelta("labels", left_labels, right_labels))
    elif label_source == "left":
        missing = sorted(set(left_labels) - set(right_labels))
        if missing:
            deltas.append(FieldDelta("labels", left_labels, right_labels))
    else:
        missing = sorted(set(right_labels) - set(left_labels))
        if missing:
            deltas.append(FieldDelta("labels", left_labels, right_labels))

    return DiffResult(deltas=deltas)
