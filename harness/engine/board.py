"""Render normalized provider issues as separate Mermaid Kanban boards."""
from __future__ import annotations

import re
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import urlparse

from harness.adapters.acli_jira import AcliJiraAdapter
from harness.adapters.base import AdapterError
from harness.adapters.github import GitHubAdapter
from harness.adapters.gitlab import GitLabAdapter
from harness.identity import UserRoster
from harness.models import IssueQuery, OpenIssue


@dataclass(frozen=True)
class IssueBoard:
    name: str
    slug: str
    ticket_url: str
    issues: tuple[OpenIssue, ...]
    error: str | None = None


TARGET_RESOURCE_ENV = {
    "gh-tts": "GH_TTS_REPO",
    "gh-helix": "GH_HELIX_REPO",
    "gl-cg": "GL_CG_REPO",
}


def collect_boards(cfg: dict, roster: UserRoster, query: IssueQuery, targets: tuple[str, ...]) -> tuple[list[IssueBoard], list[str]]:
    """Query selected providers and return boards plus sanitized failures."""
    board_urls = cfg.get("board", {})
    definitions = [
        ("GitHub.com", "github_com", "gh-tts", "gh_tts_url", os.environ.get("GITHUB_PUBLIC_HOST", "github.com")),
        ("GitHub Helix", "github_helix", "gh-helix", "gh_helix_url", os.environ.get("HELIX_GH_HOST", "github.helix.gsa.gov")),
        ("GitLab", "gitlab", "gl-cg", "gl_cg_url", cfg.get("gitlab", {}).get("host") or os.environ.get("CLOUDGOV_GLAB_HOST", "workshop.cloud.gov")),
    ]
    boards: list[IssueBoard] = []
    errors: list[str] = []
    for name, slug, target, url_key, host in definitions:
        if target not in targets:
            continue
        ticket_url = board_urls.get(url_key)
        resource = os.environ.get(TARGET_RESOURCE_ENV[target]) or _resource_from_ticket_url(target, ticket_url) or _resource_from_config(target, cfg)
        if not resource:
            _failed_board(boards, errors, name, slug, ticket_url or f"https://{host}/#TICKET#", target, f"set {TARGET_RESOURCE_ENV[target]}")
            continue
        adapter = GitLabAdapter(host, resource) if target == "gl-cg" else GitHubAdapter(host, resource)
        derived = f"https://{host}/{resource}/-/issues/#TICKET#" if target == "gl-cg" else f"https://{host}/{resource}/issues/#TICKET#"
        _query_board(boards, errors, name, slug, target, ticket_url or derived, adapter, roster, query)
    if "jira-mod" in targets:
        _collect_jira(boards, errors, cfg, board_urls, roster, query)
    return boards, errors


def _query_board(boards, errors, name, slug, target, ticket_url, adapter, roster, query) -> None:
    users = tuple(roster.resolve_issue_user(target, value) for value in query.users)
    if any(value is None for value in users):
        _failed_board(boards, errors, name, slug, ticket_url, target, "one or more email users have no roster mapping")
        return
    try:
        issues = adapter.list_issues(IssueQuery(query.relationships, users, query.state, query.labels, query.search, query.limit))
        boards.append(IssueBoard(name, slug, ticket_url, _with_ticket_url(issues, ticket_url)))
    except AdapterError as exc:
        _failed_board(boards, errors, name, slug, ticket_url, target, str(exc))


def _collect_jira(boards, errors, cfg, board_urls, roster, query) -> None:
    base_url = cfg["jira"].get("base_url") or os.environ.get("JIRA_INSTANCE_URL")
    if not base_url:
        _failed_board(boards, errors, "Jira", "jira", "", "jira-mod", "set [jira].base_url or JIRA_INSTANCE_URL")
        return
    project = os.environ.get("JIRA_MOD_PROJECT") or cfg["jira"]["project_key"]
    adapter = AcliJiraAdapter(cfg["jira"].get("acli_bin", "acli"), project)
    ticket_url = board_urls.get("jira_mod_url", f"{base_url.rstrip('/')}/browse/#TICKET#")
    users = tuple(roster.resolve_issue_user("jira-mod", value) for value in query.users)
    jira_query = IssueQuery(query.relationships, users, query.state, query.labels, query.search, query.limit)
    try:
        issues = adapter.list_issues(base_url, jira_query)
        boards.append(IssueBoard("Jira", "jira", ticket_url, _with_ticket_url(issues, ticket_url)))
    except AdapterError as exc:
        _failed_board(boards, errors, "Jira", "jira", ticket_url, "jira-mod", str(exc))


def _failed_board(boards, errors, name, slug, ticket_url, target, message) -> None:
    boards.append(IssueBoard(name, slug, ticket_url, (), message))
    errors.append(f"FAILED on {target}: {message}")


def _with_ticket_url(issues: list[OpenIssue], ticket_url: str) -> tuple[OpenIssue, ...]:
    return tuple(OpenIssue(issue.provider, issue.issue_id, issue.title, issue.body, issue.labels, ticket_url.replace("#TICKET#", issue.issue_id)) for issue in issues)


def _resource_from_ticket_url(target: str, ticket_url: str | None) -> str | None:
    if not ticket_url:
        return None
    parsed = urlparse(ticket_url)
    path = f"{parsed.path}#{parsed.fragment}".strip("/")
    suffix = "/-/issues/#TICKET#" if target == "gl-cg" else "/issues/#TICKET#"
    return path[: -len(suffix)] if path.endswith(suffix) else None


def _resource_from_config(target: str, cfg: dict) -> str | None:
    if target == "gh-tts" and cfg.get("github", {}).get("repos"):
        repo = str(cfg["github"]["repos"][0])
        return repo if "/" in repo else f"{cfg['github']['org']}/{repo}"
    return cfg.get("gitlab", {}).get("project") if target == "gl-cg" else None


def render_boards(
    boards: list[IssueBoard],
    body_limit: int = 180,
    filters: dict[str, str] | None = None,
    generated_at: str | None = None,
) -> str:
    """Render one self-contained Markdown report with provider boards and details."""
    generated_at = generated_at or datetime.now(UTC).isoformat(timespec="seconds")
    sections = [
        "# Open Issues Context",
        "",
        f"Generated: `{generated_at}`",
        f"Total issues: **{sum(len(board.issues) for board in boards)}**",
        f"Providers: **{len(boards)}**",
        "",
        "## Filters",
        "",
    ]
    for key, value in (filters or {}).items():
        sections.append(f"- **{key}:** {_md(value)}")
    sections.extend(["", "## Provider Boards", ""])
    for board in boards:
        sections.extend(_render_board(board, body_limit))
    return "\n".join(sections).rstrip() + "\n"


def _render_board(board: IssueBoard, body_limit: int) -> list[str]:
    lines = [f"### {board.name}", "", f"Issues: **{len(board.issues)}**", "", "```mermaid", "---", "config:", "  kanban:"]
    lines.extend([f"    ticketBaseUrl: '{_yaml_quote(board.ticket_url)}'", "---", "kanban"])
    lines.append(f"  {board.slug}[Open issues]")
    if board.error:
        lines.append(f'    {board.slug}_error["Provider query failed: {_mermaid(board.error)}"]')
    elif board.issues:
        for index, issue in enumerate(sorted(board.issues, key=lambda item: item.issue_id)):
            label = _card_label(issue, body_limit)
            lines.append(f'    {board.slug}_{index}["{label}"]@{{ ticket: \'{_yaml_quote(issue.issue_id)}\' }}')
    else:
        lines.append(f'    {board.slug}_empty["No open authored or assigned issues"]')
    lines.extend(["```", "", "| Issue | Title | Labels | Body |", "|---|---|---|---|"])
    if board.error:
        lines.append(f"| - | Provider query failed: {_md(board.error)} | - | - |")
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
