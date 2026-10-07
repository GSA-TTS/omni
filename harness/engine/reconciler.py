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

from harness.adapters.base import BaseIssueAdapter, BodyMode
from harness.engine.diff import compute_diff
from harness.models import CanonicalIssue, DiffResult, FieldDelta, strip_anchor

Direction = Literal["left-to-right", "right-to-left"]


@dataclass
class ReconcileResult:
    diff: DiffResult
    applied: bool
    direction: Direction | None = None
    body_mode: BodyMode = "replace"


def reconcile(
    left_adapter: BaseIssueAdapter,
    left_id: str,
    right_adapter: BaseIssueAdapter,
    right_id: str,
    direction: Direction | None = None,
    dry_run: bool = True,
    body_mode: BodyMode = "replace",
) -> ReconcileResult:
    """Diff two issues and optionally apply updates in the given direction.

    body_mode controls how the source body reaches the target:
      - "replace": overwrite the target's body with the source's (default).
      - "append":  keep the target's body and append the source's below a rule.
      - "comment": leave the target body untouched; post the source body as a
                   new comment instead.

    If dry_run is True (default), no writes occur regardless of direction.
    """
    left_issue = left_adapter.get_issue(left_id)
    right_issue = right_adapter.get_issue(right_id)
    diff = compute_diff(
        left_issue,
        right_issue,
        label_mode="additive" if direction else "exact",
        label_source="left" if direction != "right-to-left" else "right",
    )

    if dry_run or direction is None or not diff.has_changes:
        return ReconcileResult(diff=diff, applied=False, direction=direction, body_mode=body_mode)

    if direction == "left-to-right":
        _apply_patch(
            right_adapter, right_id, source=left_issue, target=right_issue, diff=diff, body_mode=body_mode
        )
    else:
        _apply_patch(
            left_adapter, left_id, source=right_issue, target=left_issue, diff=diff, body_mode=body_mode
        )

    return ReconcileResult(diff=diff, applied=True, direction=direction, body_mode=body_mode)


def _apply_patch(
    adapter: BaseIssueAdapter,
    target_id: str,
    source: CanonicalIssue,
    target: CanonicalIssue,
    diff: DiffResult,
    body_mode: BodyMode = "replace",
) -> None:
    """Write the source's content onto the target, honoring body_mode.

    "comment" mode posts the source body as a new comment and does not alter
    the target's own description -- the safest option when the target body is
    human-authored and must not be overwritten.
    """
    labels = sorted(set(source.labels) | set(target.labels))
    if body_mode == "comment":
        body_changed = _has_delta(diff.deltas, "body_markdown")
        non_body_changed = any(delta.field != "body_markdown" for delta in diff.deltas)
        if body_changed:
            adapter.add_comment(target_id, strip_anchor(source.body_markdown))
        if not non_body_changed:
            return
        patched = CanonicalIssue(
            title=source.title,
            body_markdown=target.body_markdown,
            status=source.status,
            priority=source.priority,
            labels=labels,
            assignees=list(target.assignees),
            uuid=target.uuid,
            sync_metadata=dict(target.sync_metadata),
        )
        adapter.update_issue(target_id, patched)
        return

    if body_mode == "append":
        existing = strip_anchor(target.body_markdown)
        incoming = strip_anchor(source.body_markdown)
        new_body = f"{existing}\n\n---\n\n{incoming}" if existing else incoming
    else:  # replace
        new_body = source.body_markdown

    patched = CanonicalIssue(
        title=source.title,
        body_markdown=new_body,
        status=source.status,
        priority=source.priority,
        labels=labels,
        assignees=list(target.assignees),
        uuid=target.uuid,
        sync_metadata=dict(target.sync_metadata),
    )
    adapter.update_issue(target_id, patched)


def _has_delta(deltas: list[FieldDelta], field: str) -> bool:
    return any(delta.field == field for delta in deltas)
