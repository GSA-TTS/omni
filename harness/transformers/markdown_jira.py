"""Bidirectional transformer between GitHub/GitLab Flavored Markdown (GFM)
and Atlassian Document Format (ADF), the JSON format used by Jira Cloud/Server.

This implements the common subset needed for issue sync: paragraphs, headings,
bold/italic/code marks, links, bullet/ordered lists, code blocks, and
blockquotes. Round-trips are best-effort -- ADF constructs with no Markdown
equivalent (panels, mentions, emojis) are passed through as plain text.
"""
from __future__ import annotations

import re
from typing import Any

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
_CODE_FENCE_RE = re.compile(r"^```(\w*)\s*$")
_BULLET_RE = re.compile(r"^(\s*)[-*]\s+(.*)$")
_ORDERED_RE = re.compile(r"^(\s*)\d+\.\s+(.*)$")
_BLOCKQUOTE_RE = re.compile(r"^>\s?(.*)$")

_INLINE_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\*\*(.+?)\*\*"), "strong"),
    (re.compile(r"`(.+?)`"), "code"),
    (re.compile(r"\*(.+?)\*"), "em"),
    (re.compile(r"\[(.+?)\]\((.+?)\)"), "link"),
]


def markdown_to_adf(markdown: str) -> dict[str, Any]:
    """Convert a GFM markdown string into an ADF document dict."""
    lines = (markdown or "").split("\n")
    content: list[dict[str, Any]] = []
    i = 0
    while i < len(lines):
        line = lines[i]

        if not line.strip():
            i += 1
            continue

        fence = _CODE_FENCE_RE.match(line)
        if fence:
            lang = fence.group(1)
            code_lines: list[str] = []
            i += 1
            while i < len(lines) and not _CODE_FENCE_RE.match(lines[i]):
                code_lines.append(lines[i])
                i += 1
            i += 1  # skip closing fence
            node: dict[str, Any] = {
                "type": "codeBlock",
                "content": [{"type": "text", "text": "\n".join(code_lines)}],
            }
            if lang:
                node["attrs"] = {"language": lang}
            content.append(node)
            continue

        heading = _HEADING_RE.match(line)
        if heading:
            level = len(heading.group(1))
            content.append(
                {
                    "type": "heading",
                    "attrs": {"level": level},
                    "content": _inline_to_adf(heading.group(2)),
                }
            )
            i += 1
            continue

        if _BULLET_RE.match(line) or _ORDERED_RE.match(line):
            ordered = bool(_ORDERED_RE.match(line))
            items: list[dict[str, Any]] = []
            pattern = _ORDERED_RE if ordered else _BULLET_RE
            while i < len(lines) and pattern.match(lines[i]):
                text = pattern.match(lines[i]).group(2)
                items.append(
                    {
                        "type": "listItem",
                        "content": [{"type": "paragraph", "content": _inline_to_adf(text)}],
                    }
                )
                i += 1
            content.append({"type": "orderedList" if ordered else "bulletList", "content": items})
            continue

        quote = _BLOCKQUOTE_RE.match(line)
        if quote:
            quote_lines = []
            while i < len(lines) and _BLOCKQUOTE_RE.match(lines[i]):
                quote_lines.append(_BLOCKQUOTE_RE.match(lines[i]).group(1))
                i += 1
            content.append(
                {
                    "type": "blockquote",
                    "content": [
                        {"type": "paragraph", "content": _inline_to_adf("\n".join(quote_lines))}
                    ],
                }
            )
            continue

        content.append({"type": "paragraph", "content": _inline_to_adf(line)})
        i += 1

    return {"type": "doc", "version": 1, "content": content or [{"type": "paragraph", "content": []}]}


def adf_to_markdown(adf: dict[str, Any]) -> str:
    """Convert an ADF document dict into a GFM markdown string."""
    blocks = adf.get("content", []) if isinstance(adf, dict) else []
    return "\n\n".join(_block_to_markdown(block) for block in blocks).strip()


def _block_to_markdown(block: dict[str, Any]) -> str:
    btype = block.get("type")
    content = block.get("content", [])

    if btype == "paragraph":
        return _inline_to_markdown(content)
    if btype == "heading":
        level = block.get("attrs", {}).get("level", 1)
        return f"{'#' * level} {_inline_to_markdown(content)}"
    if btype == "codeBlock":
        lang = block.get("attrs", {}).get("language", "")
        text = "".join(n.get("text", "") for n in content)
        return f"```{lang}\n{text}\n```"
    if btype == "bulletList":
        return "\n".join(f"- {_list_item_to_markdown(item)}" for item in content)
    if btype == "orderedList":
        return "\n".join(f"{idx}. {_list_item_to_markdown(item)}" for idx, item in enumerate(content, 1))
    if btype == "blockquote":
        inner = "\n".join(_block_to_markdown(b) for b in content)
        return "\n".join(f"> {line}" for line in inner.split("\n"))
    return _inline_to_markdown(content)


def _list_item_to_markdown(item: dict[str, Any]) -> str:
    paragraphs = item.get("content", [])
    return "\n  ".join(_block_to_markdown(p) for p in paragraphs)


def _inline_to_markdown(nodes: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for node in nodes or []:
        if node.get("type") != "text":
            continue
        text = node.get("text", "")
        marks = {m.get("type") for m in node.get("marks", [])}
        if "code" in marks:
            text = f"`{text}`"
        if "strong" in marks:
            text = f"**{text}**"
        if "em" in marks:
            text = f"*{text}*"
        link_mark = next((m for m in node.get("marks", []) if m.get("type") == "link"), None)
        if link_mark:
            href = link_mark.get("attrs", {}).get("href", "")
            text = f"[{text}]({href})"
        parts.append(text)
    return "".join(parts)


def _inline_to_adf(text: str) -> list[dict[str, Any]]:
    """Tokenize a single line of inline markdown into ADF text nodes."""
    if not text:
        return []

    tokens: list[dict[str, Any]] = []
    remaining = text
    while remaining:
        earliest: tuple[int, int, re.Match[str], str] | None = None
        for pattern, mark in _INLINE_PATTERNS:
            m = pattern.search(remaining)
            if m and (earliest is None or m.start() < earliest[0]):
                earliest = (m.start(), m.end(), m, mark)

        if earliest is None:
            tokens.append({"type": "text", "text": remaining})
            break

        start, end, match, mark = earliest
        if start > 0:
            tokens.append({"type": "text", "text": remaining[:start]})

        if mark == "link":
            tokens.append(
                {
                    "type": "text",
                    "text": match.group(1),
                    "marks": [{"type": "link", "attrs": {"href": match.group(2)}}],
                }
            )
        else:
            tokens.append({"type": "text", "text": match.group(1), "marks": [{"type": mark}]})

        remaining = remaining[end:]

    return tokens
