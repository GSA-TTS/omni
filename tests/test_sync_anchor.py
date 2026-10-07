from harness.models import CanonicalIssue, parse_anchor, strip_anchor


def test_strip_anchor_removes_footer_only():
    body = (
        "### Summary\nUpdate the OIDC endpoints.\n\n"
        "<!-- fed-sync-anchor: urn:fed:sync:a1b2c3d4 -->\n"
        "<!-- links: gh-tts:12 | gh-helix:4 | gl-cg:88 | jira:PROJECT-402 -->"
    )
    cleaned = strip_anchor(body)
    assert cleaned == "### Summary\nUpdate the OIDC endpoints."
    assert "fed-sync-anchor" not in cleaned


def test_strip_anchor_preserves_user_html_comments():
    """Only the anchor+links pair should be stripped; other HTML comments survive."""
    body = (
        "Note: <!-- keep me --> this is important.\n\n"
        "<!-- fed-sync-anchor: urn:fed:sync:xyz -->\n"
        "<!-- links: jira:PROJ-1 -->"
    )
    cleaned = strip_anchor(body)
    assert "<!-- keep me -->" in cleaned
    assert "fed-sync-anchor" not in cleaned


def test_parse_anchor_extracts_uuid_and_links():
    body = (
        "Body text\n\n"
        "<!-- fed-sync-anchor: urn:fed:sync:a1b2c3d4 -->\n"
        "<!-- links: gh-tts:12 | gl-cg:88 -->"
    )
    anchor, links = parse_anchor(body)
    assert anchor == "urn:fed:sync:a1b2c3d4"
    assert links == {"gh-tts": "12", "gl-cg": "88"}


def test_parse_anchor_missing_returns_none():
    anchor, links = parse_anchor("No footer here.")
    assert anchor is None
    assert links == {}


def test_body_with_anchor_round_trips_through_strip():
    issue = CanonicalIssue.create_new(title="T", body_markdown="Original body")
    issue.sync_metadata = {"gh-tts": "12", "gl-cg": "88"}
    rendered = issue.body_with_anchor()

    anchor, links = parse_anchor(rendered)
    assert anchor == issue.uuid
    assert links == {"gh-tts": "12", "gl-cg": "88"}
    assert strip_anchor(rendered) == "Original body"


def test_cross_target_update_does_not_duplicate_anchor():
    """Re-rendering an already-anchored issue must not accumulate footers."""
    issue = CanonicalIssue.create_new(title="T", body_markdown="Body")
    issue.sync_metadata = {"gl-cg": "88"}
    once = issue.body_with_anchor()

    issue.body_markdown = once  # simulate re-fetching the issue with footer attached
    issue.sync_metadata = {"gl-cg": "88", "gh-helix": "4"}
    twice = issue.body_with_anchor()

    assert twice.count("fed-sync-anchor") == 1
    assert "gh-helix:4" in twice
