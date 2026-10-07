from harness.engine.diff import compute_diff
from harness.models import CanonicalIssue


def _issue(**overrides) -> CanonicalIssue:
    base = dict(
        title="Title",
        body_markdown="Body",
        status="OPEN",
        labels=["a"],
        assignees=["jdoe"],
    )
    base.update(overrides)
    return CanonicalIssue(**base)


def test_no_diff_when_identical():
    left = _issue()
    right = _issue()
    result = compute_diff(left, right)
    assert not result.has_changes


def test_detects_title_change():
    left = _issue(title="Old title")
    right = _issue(title="New title")
    result = compute_diff(left, right)
    assert result.has_changes
    assert any(d.field == "title" for d in result.deltas)


def test_detects_status_change():
    left = _issue(status="OPEN")
    right = _issue(status="CLOSED")
    result = compute_diff(left, right)
    assert any(d.field == "status" for d in result.deltas)


def test_label_order_does_not_trigger_diff():
    left = _issue(labels=["a", "b"])
    right = _issue(labels=["b", "a"])
    result = compute_diff(left, right)
    assert not result.has_changes


def test_additive_label_diff_ignores_target_only_labels():
    left = _issue(labels=["bug"])
    right = _issue(labels=["bug", "human-owned"])
    result = compute_diff(left, right, label_mode="additive", label_source="left")
    assert not result.has_changes


def test_additive_label_diff_detects_missing_source_labels():
    left = _issue(labels=["bug", "area:sync"])
    right = _issue(labels=["bug", "human-owned"])
    result = compute_diff(left, right, label_mode="additive", label_source="left")
    assert any(d.field == "labels" for d in result.deltas)


def test_anchor_footer_stripped_before_body_diff():
    left = _issue(
        body_markdown="Body\n\n<!-- fed-sync-anchor: urn:fed:sync:abc -->\n<!-- links: gh-tts:12 -->"
    )
    right = _issue(
        body_markdown="Body\n\n<!-- fed-sync-anchor: urn:fed:sync:xyz -->\n<!-- links: gl-cg:88 -->"
    )
    result = compute_diff(left, right)
    assert not result.has_changes
