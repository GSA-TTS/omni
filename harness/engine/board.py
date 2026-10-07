"""Render normalized provider issues as separate Mermaid Kanban boards."""
from __future__ import annotations

import re
from dataclasses import dataclass

from harness.models import OpenIssue


@dataclass(frozen=True)
class IssueBoard:
    name: str
    slug: str
    ticket_url: str
    issues: tuple[OpenIssue, ...]
    error: str | None = None


def render_boards(boards: list[IssueBoard], body_limit: int = 180) -> str:
    """Render one Mermaid board per provider plus directly linked details."""
    sections = ["# My Open Issues", ""]
    for board in boards:
        sections.extend(_render_board(board, body_limit))
    return "\n".join(sections).rstrip() + "\n"


def _render_board(board: IssueBoard, body_limit: int) -> list[str]:
    lines = [f"## {board.name}", "", "```mermaid", "---", "config:", "  kanban:"]
    lines.extend([f"    ticketBaseUrl: '{_yaml_quote(board.ticket_url)}'", "---", "kanban"])
    lines.append(f"  {board.slug}[Open issues]")
    if board.error:
        lines.append(f'    {board.slug}_error["Provider query failed; see stderr"]')
    elif board.issues:
        for index, issue in enumerate(sorted(board.issues, key=lambda item: item.issue_id)):
            label = _card_label(issue, body_limit)
            lines.append(f'    {board.slug}_{index}["{label}"]@{{ ticket: \'{_yaml_quote(issue.issue_id)}\' }}')
    else:
        lines.append(f'    {board.slug}_empty["No open authored or assigned issues"]')
    lines.extend(["```", "", "| Issue | Title | Labels | Body |", "|---|---|---|---|"])
    if board.error:
        lines.append("| - | Provider query failed; see stderr | - | - |")
    elif board.issues:
        for issue in sorted(board.issues, key=lambda item: item.issue_id):
            labels = ", ".join(issue.labels) or "-"
            lines.append(
                f"| [{_md(issue.issue_id)}]({issue.url}) | {_md(issue.title)} | "
                f"{_md(labels)} | {_md(_truncate(issue.body, body_limit))} |"
            )
    else:
        lines.append("| - | No open authored or assigned issues | - | - |")
    lines.append("")
    return lines


def _card_label(issue: OpenIssue, body_limit: int) -> str:
    labels = ", ".join(issue.labels) or "none"
    parts = [issue.issue_id, issue.title, f"Labels: {labels}", _truncate(issue.body, body_limit)]
    return "<br/>".join(_mermaid(part) for part in parts if part)


def _truncate(value: str, limit: int) -> str:
    compact = re.sub(r"\s+", " ", value or "").strip()
    return compact if len(compact) <= limit else compact[: max(0, limit - 3)].rstrip() + "..."


def _mermaid(value: str) -> str:
    return value.replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;").replace(">", "&gt;")


def _md(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").replace("|", "\\|").strip()


def _yaml_quote(value: str) -> str:
    return value.replace("'", "''")
