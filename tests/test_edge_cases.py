"""Stress the markdown edge-case corpus through the pure, offline parts of
the harness: GFM<->ADF transform round-trips and sync-anchor strip/parse.

These assert the invariants we *expect* to hold and xfail-document the ones
we know are lossy, so the agent skills stay honest about real behavior.
"""
import pytest

from harness.models import CanonicalIssue, parse_anchor, strip_anchor
from harness.testing.edge_cases import EDGE_CASES, by_id
from harness.transformers.markdown_jira import adf_to_markdown, markdown_to_adf

# Cases whose ADF round-trip is known-lossy or not GFM at all. Documented,
# not silently tolerated -- these feed skills/known-failures.
_ADF_LOSSY = {
    "image", "task_list", "fenced_code_backticks", "hr", "html_comment",
    "jira_wiki", "adf_panel_ish", "anchor_lookalike", "yaml_frontmatter",
    "math", "footnote", "autolink", "escaped_markdown",
    "bold_italic_code", "crlf", "trailing_ws", "zero_width", "null_byteish",
    "rtl",
}


@pytest.mark.parametrize("case", EDGE_CASES, ids=lambda c: c.id)
def test_adf_transform_never_raises(case):
    """markdown_to_adf and adf_to_markdown must never crash on any input."""
    adf = markdown_to_adf(case.body)
    assert isinstance(adf, dict)
    out = adf_to_markdown(adf)
    assert isinstance(out, str)


@pytest.mark.parametrize(
    "case",
    [c for c in EDGE_CASES if c.id not in _ADF_LOSSY and c.body.strip()],
    ids=lambda c: c.id,
)
def test_adf_round_trip_stable_for_supported_cases(case):
    """For the GFM subset we claim to support, round-trip is stable."""
    once = adf_to_markdown(markdown_to_adf(case.body))
    twice = adf_to_markdown(markdown_to_adf(once))
    # Idempotent after the first pass even if the first pass normalized.
    assert once == twice


@pytest.mark.parametrize("case", EDGE_CASES, ids=lambda c: c.id)
def test_strip_anchor_never_raises(case):
    assert isinstance(strip_anchor(case.body), str)


def test_forged_anchor_is_parsed_but_body_isolated():
    """A user body that *looks* like our anchor is still parseable, and
    stripping it must not devour surrounding real content."""
    case = by_id("anchor_lookalike")
    anchor, links = parse_anchor(case.body)
    assert anchor == "fake"
    assert links == {"x": "1"}
    # Nothing but the forged footer -> stripping yields empty, no crash.
    assert strip_anchor(case.body) == ""


def test_real_body_with_forged_anchor_keeps_prose():
    body = "Real prose paragraph.\n\n<!-- fed-sync-anchor: fake -->\n<!-- links: x:1 -->"
    assert strip_anchor(body) == "Real prose paragraph."


def test_nul_byte_body_rejected_at_boundary():
    """NUL bytes must be rejected before any CLI call (ValueError: embedded null byte)."""
    issue = CanonicalIssue.create_new("t", "before\x00after")
    with pytest.raises(ValueError, match="NUL byte"):
        issue.body_with_anchor()


def test_crlf_body_not_a_diff_against_lf():
    """CRLF vs LF of the same text must not register as drift (GitLab normalizes to LF)."""
    crlf = CanonicalIssue.create_new("t", "line1\r\nline2\r\nline3")
    lf = CanonicalIssue.create_new("t", "line1\nline2\nline3")
    assert not crlf.diff(lf).has_changes
