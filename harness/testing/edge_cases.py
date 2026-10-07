"""Curated markdown edge-case corpus for stress-testing provider CLI
compatibility (gh/glab/acli issue bodies and comments).

Each case pairs a short id with a body string that exercises a construct
known to break shell quoting, provider parsers, or round-trip fidelity. The
goal is to find where each CLI loses or mangles content so the behavior can
be documented in the agent skills (see skills/).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EdgeCase:
    id: str
    body: str
    note: str


EDGE_CASES: list[EdgeCase] = [
    EdgeCase("plain", "A simple one-line body.", "baseline"),
    EdgeCase("empty", "", "empty body"),
    EdgeCase("heading", "# H1\n## H2\n### H3", "ATX headings"),
    EdgeCase("bold_italic_code", "**bold** _italic_ `code` ~~strike~~", "inline marks"),
    EdgeCase(
        "link",
        "See [docs](https://example.com/a?b=c&d=e#frag).",
        "link w/ query+fragment",
    ),
    EdgeCase("image", "![alt](https://example.com/x.png)", "image syntax"),
    EdgeCase("ul", "- a\n- b\n  - nested\n- c", "nested unordered list"),
    EdgeCase("ol", "1. first\n2. second\n3. third", "ordered list"),
    EdgeCase("task_list", "- [ ] todo\n- [x] done", "GFM task list"),
    EdgeCase("table", "| a | b |\n|---|---|\n| 1 | 2 |", "GFM table"),
    EdgeCase(
        "fenced_code", "```python\nprint('hi')\n# comment\n```", "fenced code block"
    ),
    EdgeCase(
        "fenced_code_backticks",
        "````\n```nested```\n````",
        "quad-fence wrapping triple",
    ),
    EdgeCase("blockquote", "> quoted\n> multi-line", "blockquote"),
    EdgeCase(
        "hr", "above\n\n---\n\nbelow", "horizontal rule (anchor-footer collision risk)"
    ),
    EdgeCase(
        "html_comment",
        "text <!-- hidden --> more",
        "html comment (sync-anchor collision)",
    ),
    EdgeCase(
        "backticks_shell",
        "run `rm -rf /tmp/x` carefully",
        "backticks (shell command-substitution risk)",
    ),
    EdgeCase(
        "dollar_subshell",
        "value is $(whoami) and ${HOME}",
        "shell subshell/var expansion risk",
    ),
    EdgeCase(
        "double_quotes",
        'He said "hello" to the "world".',
        "double quotes (shell quoting)",
    ),
    EdgeCase("single_quotes", "it's a 'quoted' word", "single quotes"),
    EdgeCase("backslashes", "path C:\\Users\\x and regex \\d+\\.\\d+", "backslashes"),
    EdgeCase("pipes", "a | b | c and `grep x | wc -l`", "pipes (table + shell)"),
    EdgeCase("ampersand_semicolon", "foo && bar; baz & qux", "shell control operators"),
    EdgeCase(
        "angle_brackets",
        "generics List<Map<String,Int>> and <tag>",
        "angle brackets / redirection",
    ),
    EdgeCase(
        "leading_dash", "-not-a-flag and --also-not", "leading dashes (arg parsing)"
    ),
    EdgeCase(
        "unicode", "émoji 🚀 — café, naïve, 日本語, Ωμέγα", "unicode + emoji + em dash"
    ),
    EdgeCase("rtl", "mixed עברית and English", "right-to-left text"),
    EdgeCase("zero_width", "a\u200bb\u200cc", "zero-width characters"),
    EdgeCase("crlf", "line1\r\nline2\r\nline3", "CRLF line endings"),
    EdgeCase("tabs", "col1\tcol2\tcol3", "tab characters"),
    EdgeCase("trailing_ws", "trailing spaces   \nand more  ", "trailing whitespace"),
    EdgeCase("long_line", "x" * 5000, "very long single line"),
    EdgeCase(
        "jira_wiki",
        "h1. Heading\n{code}block{code}\n*bold*",
        "Jira wiki markup (not GFM)",
    ),
    EdgeCase(
        "adf_panel_ish", ":::info\npanel body\n:::", "fenced-directive (ADF panel-like)"
    ),
    EdgeCase(
        "anchor_lookalike",
        "<!-- fed-sync-anchor: fake -->\n<!-- links: x:1 -->",
        "forged sync anchor",
    ),
    EdgeCase("null_byteish", "before\x00after", "NUL byte (illegal in many CLIs)"),
    EdgeCase(
        "yaml_frontmatter",
        "---\ntitle: x\n---\nbody",
        "yaml front matter (hr collision)",
    ),
    EdgeCase("math", "inline $E = mc^2$ and $$\\int_0^1 x\\,dx$$", "LaTeX math"),
    EdgeCase("footnote", "text[^1]\n\n[^1]: the note", "GFM footnote"),
    EdgeCase("autolink", "<https://example.com> and user@example.com", "autolinks"),
    EdgeCase(
        "escaped_markdown", "\\*not italic\\* and \\`not code\\`", "escaped markdown"
    ),
]


def by_id(case_id: str) -> EdgeCase:
    for case in EDGE_CASES:
        if case.id == case_id:
            return case
    raise KeyError(case_id)
