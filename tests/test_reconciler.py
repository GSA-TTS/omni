from harness.adapters.base import BaseIssueAdapter
from harness.engine.reconciler import reconcile
from harness.models import CanonicalIssue


class FakeAdapter(BaseIssueAdapter):
    """In-memory adapter for exercising the reconciler without subprocess calls."""

    def __init__(self, issue: CanonicalIssue):
        self.issue = issue
        self.updated_with: CanonicalIssue | None = None

    def get_issue(self, issue_id: str) -> CanonicalIssue:
        return self.issue

    def create_issue(self, issue: CanonicalIssue) -> str:
        raise NotImplementedError

    def update_issue(self, issue_id: str, issue: CanonicalIssue) -> None:
        self.updated_with = issue


def test_dry_run_never_applies_changes():
    left = FakeAdapter(CanonicalIssue.create_new(title="Left title", body_markdown="B"))
    right = FakeAdapter(
        CanonicalIssue.create_new(title="Right title", body_markdown="B")
    )

    result = reconcile(left, "1", right, "2", direction="left-to-right", dry_run=True)

    assert result.diff.has_changes
    assert not result.applied
    assert right.updated_with is None


def test_left_to_right_applies_left_as_source_of_truth():
    left = FakeAdapter(CanonicalIssue.create_new(title="Left title", body_markdown="B"))
    right = FakeAdapter(
        CanonicalIssue.create_new(title="Right title", body_markdown="B")
    )

    result = reconcile(left, "1", right, "2", direction="left-to-right", dry_run=False)

    assert result.applied
    assert right.updated_with is not None
    assert right.updated_with.title == "Left title"
    assert left.updated_with is None if hasattr(left, "updated_with") else True


def test_right_to_left_applies_right_as_source_of_truth():
    left = FakeAdapter(CanonicalIssue.create_new(title="Left title", body_markdown="B"))
    right = FakeAdapter(
        CanonicalIssue.create_new(title="Right title", body_markdown="B")
    )

    result = reconcile(left, "1", right, "2", direction="right-to-left", dry_run=False)

    assert result.applied
    assert left.updated_with is not None
    assert left.updated_with.title == "Right title"


def test_no_op_when_no_changes_detected():
    left = FakeAdapter(CanonicalIssue.create_new(title="Same", body_markdown="B"))
    right = FakeAdapter(CanonicalIssue.create_new(title="Same", body_markdown="B"))

    result = reconcile(left, "1", right, "2", direction="left-to-right", dry_run=False)

    assert not result.diff.has_changes
    assert not result.applied
    assert right.updated_with is None
