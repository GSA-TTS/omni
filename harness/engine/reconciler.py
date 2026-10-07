"""Reconciles drift between two provider issues: dry-run preview or apply
a one-directional patch using one side as the source of truth.

Loop prevention: callers are expected to pass distinct (adapter, issue_id)
pairs per sync edge. The reconciler itself performs no cross-edge bookkeeping;
anchor UUIDs in body_with_anchor() are what let the CLI avoid re-processing
an issue it just wrote (see cli.py's sync command).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from harness.adapters.base import BaseIssueAdapter
from harness.engine.diff import compute_diff
from harness.models import CanonicalIssue, DiffResult

Direction = Literal["left-to-right", "right-to-left"]


@dataclass
class ReconcileResult:
    diff: DiffResult
    applied: bool
    direction: Direction | None = None


def reconcile(
    left_adapter: BaseIssueAdapter,
    left_id: str,
    right_adapter: BaseIssueAdapter,
    right_id: str,
    direction: Direction | None = None,
    dry_run: bool = True,
) -> ReconcileResult:
    """Diff two issues and optionally apply updates in the given direction.

    If dry_run is True (default), no writes occur regardless of direction.
    """
    left_issue = left_adapter.get_issue(left_id)
    right_issue = right_adapter.get_issue(right_id)
    diff = compute_diff(left_issue, right_issue)

    if dry_run or direction is None or not diff.has_changes:
        return ReconcileResult(diff=diff, applied=False, direction=direction)

    if direction == "left-to-right":
        _apply_patch(right_adapter, right_id, source=left_issue, target=right_issue)
    else:
        _apply_patch(left_adapter, left_id, source=right_issue, target=left_issue)

    return ReconcileResult(diff=diff, applied=True, direction=direction)


def _apply_patch(
    adapter: BaseIssueAdapter, target_id: str, source: CanonicalIssue, target: CanonicalIssue
) -> None:
    """Build a patched issue carrying the target's identity/metadata but the
    source's content, then write it through the target's adapter."""
    patched = CanonicalIssue(
        title=source.title,
        body_markdown=source.body_markdown,
        status=source.status,
        priority=source.priority,
        labels=list(source.labels),
        assignees=list(target.assignees),
        uuid=target.uuid,
        sync_metadata=dict(target.sync_metadata),
    )
    adapter.update_issue(target_id, patched)
