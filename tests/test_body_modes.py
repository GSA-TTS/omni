from harness.adapters.base import BaseIssueAdapter
from harness.engine.reconciler import reconcile
from harness.models import CanonicalIssue


class RecordingAdapter(BaseIssueAdapter):
    """Captures update_issue/add_comment calls without touching a real CLI."""

    def __init__(self, issue: CanonicalIssue):
        self.issue = issue
        self.updated: CanonicalIssue | None = None
        self.comments: list[str] = []

    def get_issue(self, issue_id: str) -> CanonicalIssue:
        return self.issue

    def create_issue(self, issue: CanonicalIssue) -> str:
        raise NotImplementedError

    def update_issue(self, issue_id: str, issue: CanonicalIssue) -> None:
        self.updated = issue

    def add_comment(self, issue_id: str, body: str) -> None:
        self.comments.append(body)


def _pair():
    left = RecordingAdapter(CanonicalIssue.create_new("Title", "SOURCE body"))
    right = RecordingAdapter(CanonicalIssue.create_new("Title", "TARGET body"))
    return left, right


def test_replace_overwrites_target_body():
    left, right = _pair()
    reconcile(left, "1", right, "2", direction="left-to-right", dry_run=False, body_mode="replace")
    assert right.updated is not None
    assert "SOURCE body" in right.updated.body_markdown
    assert "TARGET body" not in right.updated.body_markdown
    assert right.comments == []


def test_append_preserves_target_and_adds_source():
    left, right = _pair()
    reconcile(left, "1", right, "2", direction="left-to-right", dry_run=False, body_mode="append")
    assert right.updated is not None
    assert "TARGET body" in right.updated.body_markdown
    assert "SOURCE body" in right.updated.body_markdown
    assert "---" in right.updated.body_markdown  # separator rule
    assert right.comments == []


def test_comment_mode_leaves_body_untouched():
    left, right = _pair()
    reconcile(left, "1", right, "2", direction="left-to-right", dry_run=False, body_mode="comment")
    assert right.updated is None  # body never rewritten
    assert right.comments == ["SOURCE body"]


def test_dry_run_writes_nothing_in_any_mode():
    for mode in ("replace", "append", "comment"):
        left, right = _pair()
        reconcile(left, "1", right, "2", direction="left-to-right", dry_run=True, body_mode=mode)
        assert right.updated is None
        assert right.comments == []


def test_result_records_body_mode():
    left, right = _pair()
    result = reconcile(left, "1", right, "2", direction="left-to-right", dry_run=True, body_mode="append")
    assert result.body_mode == "append"
