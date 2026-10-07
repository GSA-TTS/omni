import tomllib

from harness.config import (
    email_to_login_map,
    map_assignee,
    map_labels,
    milestone_label,
    sanitize_jira_label,
)

_CFG = tomllib.loads(
    """
[jira]
project_key = "FPDF"
[github]
org = "GSA-TTS"
repos = ["r1"]
[sync]
milestone_label_prefix = "milestone:"
[developers]
gh-login-1 = "person.one@agency.gov"
[labels]
"priority:high" = "priority-high"
[always_apply]
jira_labels = ["github-sync"]
"""
)


def test_sanitize_replaces_spaces_with_hyphens():
    assert sanitize_jira_label("PI 6 Iteration 6.1") == "PI-6-Iteration-6.1"


def test_map_labels_applies_mapping_and_always_apply():
    out = map_labels(["priority:high", "custom label"], _CFG)
    assert "priority-high" in out
    assert "custom-label" in out
    assert "github-sync" in out


def test_map_labels_passes_through_unlisted():
    out = map_labels(["area:ocr"], _CFG)
    assert "area:ocr" in out


def test_map_assignee_case_insensitive():
    assert map_assignee(["jjediny"], _CFG) == "person.one@agency.gov"


def test_map_assignee_returns_none_when_unmapped():
    assert map_assignee(["unknown-login"], _CFG) is None


def test_email_to_login_map_inverts_developers():
    inv = email_to_login_map(_CFG)
    assert inv["person.one@agency.gov"] == "gh-login-1"


def test_milestone_label_encodes_prefix_and_sanitizes():
    assert milestone_label("PI 6 Iteration 6.1", _CFG) == "milestone:PI-6-Iteration-6.1"


def test_milestone_label_none_passthrough():
    assert milestone_label(None, _CFG) is None
