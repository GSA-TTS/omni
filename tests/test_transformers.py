from hypothesis import given
from hypothesis import strategies as st

from harness.transformers.markdown_jira import adf_to_markdown, markdown_to_adf


def test_heading_round_trip():
    md = "### Summary"
    adf = markdown_to_adf(md)
    assert adf["content"][0]["type"] == "heading"
    assert adf["content"][0]["attrs"]["level"] == 3
    assert adf_to_markdown(adf) == md


def test_bold_italic_code_marks():
    md = "This has **bold**, *italic*, and `code`."
    adf = markdown_to_adf(md)
    text_nodes = adf["content"][0]["content"]
    marks = [n.get("marks", [{}])[0].get("type") for n in text_nodes if n.get("marks")]
    assert "strong" in marks
    assert "em" in marks
    assert "code" in marks


def test_link_round_trip():
    md = "See [the docs](https://example.com/docs) for details."
    adf = markdown_to_adf(md)
    assert adf_to_markdown(adf) == md


def test_bullet_list_round_trip():
    md = "- first item\n- second item"
    adf = markdown_to_adf(md)
    assert adf["content"][0]["type"] == "bulletList"
    assert adf_to_markdown(adf) == md


def test_ordered_list_round_trip():
    md = "1. first item\n2. second item"
    adf = markdown_to_adf(md)
    assert adf["content"][0]["type"] == "orderedList"
    assert adf_to_markdown(adf) == md


def test_code_block_round_trip():
    md = "```python\nprint('hi')\n```"
    adf = markdown_to_adf(md)
    assert adf["content"][0]["type"] == "codeBlock"
    assert adf_to_markdown(adf) == md


def test_blockquote_round_trip():
    md = "> quoted text"
    adf = markdown_to_adf(md)
    assert adf["content"][0]["type"] == "blockquote"
    assert adf_to_markdown(adf) == md


_SAFE_TEXT = st.text(
    alphabet=st.characters(
        blacklist_categories=("Cs",), blacklist_characters="\n\r*`[]<>#>-"
    ),
    min_size=1,
    max_size=40,
).filter(lambda s: s.strip() != "")


@given(_SAFE_TEXT)
def test_plain_paragraph_round_trip_property(text: str):
    """Plain text with no markdown syntax should survive a full ADF round trip.

    Leading/trailing whitespace is not semantically meaningful in markdown
    paragraphs, so it is stripped before comparison.
    """
    adf = markdown_to_adf(text)
    assert adf_to_markdown(adf) == text.strip()
