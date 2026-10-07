"""Adapter wrapping the Atlassian CLI (`acli jira workitem`) for GSA FedRAMP
GovCloud Jira. Transposed from the TTSE petrified-forest sync tooling.

Critical design rule (from a 2026-09-21 incident): this adapter NEVER
read-modify-writes `fields.description`. Round-tripping ADF through plain
text flattened rich formatting on ~82 real tickets. Sync state is written to
a single dedicated **comment** identified by a leading marker line, and only
labels/assignee are ever edited.

`acli` can only write summary, description, type, assignee, and labels -- it
has no flag for Sprint/Fix Version, so GitHub milestones are encoded as a
prefixed Jira label (see config.milestone_label).
"""
from __future__ import annotations

import re
from datetime import UTC, datetime

from harness.adapters.base import AdapterError, BaseIssueAdapter
from harness.models import CanonicalIssue, IssueQuery, OpenIssue

SYNC_COMMENT_MARKER = "[github-sync]"
_VIEW_FIELDS = "summary,status,assignee,labels"


class AcliJiraAdapter(BaseIssueAdapter):
    """GSA GovCloud Jira adapter via `acli jira workitem`.

    Writes labels + assignee + an idempotent sync comment; never touches the
    description field. Milestones arrive pre-encoded as labels by the caller.
    """

    def __init__(self, acli_bin: str = "acli", project_key: str = "FPDF"):
        self.acli_bin = acli_bin
        self.project_key = project_key
        self._view_cache: dict[str, dict | None] = {}

    # ---- reads -------------------------------------------------------------

    def _view(self, issue_id: str) -> dict | None:
        """Fetch (and cache) a workitem's fields, returning None if missing/forbidden.

        A single view per key avoids 4 redundant `acli` calls per ticket and
        lets a GitHub reference to a nonexistent Jira key be skipped instead
        of crashing the whole run.
        """
        if issue_id in self._view_cache:
            return self._view_cache[issue_id]
        try:
            data = self._run_cli(
                [self.acli_bin, "jira", "workitem", "view", issue_id, "--fields", _VIEW_FIELDS, "--json"],
            )
        except AdapterError:
            data = None
        result = data if isinstance(data, dict) else None
        self._view_cache[issue_id] = result
        return result

    def exists(self, issue_id: str) -> bool:
        """Whether the Jira key is visible to the current user."""
        return self._view(issue_id) is not None

    def get_issue(self, issue_id: str) -> CanonicalIssue:
        data = self._view(issue_id)
        if data is None:
            raise AdapterError(f"Jira workitem {issue_id} does not exist or is not visible")
        fields = data.get("fields", {})
        status_cat = ((fields.get("status") or {}).get("statusCategory") or {}).get("name")
        assignee = fields.get("assignee") or {}
        return CanonicalIssue(
            title=fields.get("summary", ""),
            body_markdown="",  # description is intentionally never read (see module docstring)
            status="CLOSED" if status_cat == "Done" else "OPEN",
            labels=list(fields.get("labels") or []),
            assignees=[assignee["emailAddress"]] if assignee.get("emailAddress") else [],
        )

    def status_category(self, issue_id: str) -> str | None:
        """Return the raw Jira status category name (e.g. 'Done') or None."""
        data = self._view(issue_id)
        if data is None:
            return None
        return (((data.get("fields") or {}).get("status") or {}).get("statusCategory") or {}).get("name")

    def labels(self, issue_id: str) -> set[str]:
        data = self._view(issue_id)
        if data is None:
            return set()
        return set((data.get("fields") or {}).get("labels") or [])

    def current_assignee_email(self, issue_id: str) -> str | None:
        data = self._view(issue_id)
        if data is None:
            return None
        return ((data.get("fields") or {}).get("assignee") or {}).get("emailAddress")

    def list_issues(self, base_url: str, query: IssueQuery) -> list[OpenIssue]:
        """List Jira work matching normalized relationship and content filters."""
        people = []
        for relationship in query.relationships:
            field = "reporter" if relationship == "authored" else "assignee"
            people.extend(
                f"{field} = currentUser()" if user == "@me" else f'{field} = "{_jql(user)}"'
                for user in query.users
            )
        clauses = [f'project = "{_jql(self.project_key)}"', f"({' OR '.join(people)})"]
        if query.state == "open":
            clauses.append("statusCategory != Done")
        elif query.state == "closed":
            clauses.append("statusCategory = Done")
        clauses.extend(f'labels = "{_jql(label)}"' for label in query.labels)
        if query.search:
            clauses.append(f'text ~ "{_jql(query.search)}"')
        jql = " AND ".join(clauses)
        data = self._run_cli(
            [
                self.acli_bin, "jira", "workitem", "search", "--jql", jql,
                "--fields", "key,summary,description,labels", "--limit", str(query.limit), "--json",
            ]
        )
        items = data.get("issues", []) if isinstance(data, dict) else data
        if not isinstance(items, list):
            raise AdapterError(f"Unexpected Jira workitem search output for {self.project_key}")
        return [
            OpenIssue(
                provider="jira-mod",
                issue_id=str(item.get("key") or ""),
                title=(item.get("fields") or {}).get("summary") or item.get("summary") or "",
                body=_adf_text((item.get("fields") or {}).get("description") or item.get("description")),
                labels=tuple((item.get("fields") or {}).get("labels") or item.get("labels") or []),
                url=f"{base_url.rstrip('/')}/browse/{item.get('key')}",
            )
            for item in items
            if item.get("key")
        ]

    # ---- writes ------------------------------------------------------------

    def create_issue(self, issue: CanonicalIssue) -> str:
        argv = [
            self.acli_bin,
            "jira",
            "workitem",
            "create",
            "--project",
            self.project_key,
            "--type",
            "Task",
            "--summary",
            issue.title,
        ]
        if issue.labels:
            argv += ["--labels", ",".join(sorted(set(issue.labels)))]
        key = self._run_cli(argv, parse_json=False)
        return str(key).strip()

    def update_issue(self, issue_id: str, issue: CanonicalIssue) -> None:
        """Full canonical update: reconcile labels and assignee only.

        Description is never written. Status transitions require workflow
        knowledge and are left to the Jira UI.
        """
        self.edit(
            issue_id,
            assignee=issue.assignees[0] if issue.assignees else None,
            add_labels=issue.labels,
        )

    def edit(
        self,
        issue_id: str,
        *,
        assignee: str | None = None,
        add_labels: list[str] | None = None,
        remove_labels: list[str] | None = None,
        dry_run: bool = False,
    ) -> tuple[bool, str]:
        """Apply a labels/assignee edit. Returns (ok, message). Never writes description."""
        cmd = [self.acli_bin, "jira", "workitem", "edit", "--key", issue_id, "--yes"]
        base_len = len(cmd)
        if assignee:
            cmd += ["--assignee", assignee]
        if add_labels:
            cmd += ["--labels", ",".join(sorted(set(add_labels)))]
        if remove_labels:
            cmd += ["--remove-labels", ",".join(sorted(set(remove_labels)))]

        if len(cmd) == base_len:  # nothing to change beyond --key/--yes
            return True, "no-op"
        if dry_run:
            return True, "dry-run: " + " ".join(cmd)

        try:
            self._run_cli(cmd, parse_json=False)
        except AdapterError as exc:
            return False, str(exc)[:400]
        return True, "updated"

    # ---- comments ----------------------------------------------------------

    def list_comments(self, issue_id: str) -> list[dict]:
        data = self._run_cli(
            [self.acli_bin, "jira", "workitem", "comment", "list", "--key", issue_id, "--json"],
        )
        if isinstance(data, dict):
            comments = data.get("comments")
            if isinstance(comments, list):
                return comments
        raise AdapterError(f"Invalid comment list response for Jira workitem {issue_id}")

    def upsert_sync_comment(
        self, issue_id: str, body: str, *, dry_run: bool = False
    ) -> tuple[bool, str]:
        """Create or update the single marked sync comment in place.

        Finds our comment by its leading marker line (matched on content, not
        author, so it survives credential rotation). Never touches any other
        comment or the description field.
        """
        existing = find_sync_comment(self.list_comments(issue_id))

        if dry_run:
            return True, f"dry-run: comment {'update' if existing else 'create'} on {issue_id}"

        if existing:
            cmd = [
                self.acli_bin, "jira", "workitem", "comment", "update",
                "--key", issue_id, "--id", existing["id"], "--body", body,
            ]
            verb = "updated"
        else:
            cmd = [
                self.acli_bin, "jira", "workitem", "comment", "create",
                "--key", issue_id, "--body", body,
            ]
            verb = "created"

        try:
            self._run_cli(cmd, parse_json=False)
        except AdapterError as exc:
            return False, str(exc)[:400]
        return True, f"comment {verb}"


def find_sync_comment(comments: list[dict]) -> dict | None:
    """Return one marked sync comment, failing closed when markers are ambiguous."""
    matches = [
        comment
        for comment in comments
        if str(comment.get("body") or "").lstrip().startswith(SYNC_COMMENT_MARKER)
    ]
    if len(matches) > 1:
        raise AdapterError("Multiple managed Jira sync comments found; refusing an ambiguous update")
    return matches[0] if matches else None


def _adf_text(value: object) -> str:
    """Flatten Jira ADF to readable text without interpreting its structure."""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return " ".join(filter(None, (_adf_text(item) for item in value)))
    if isinstance(value, dict):
        text = value.get("text")
        if isinstance(text, str):
            return text
        return _adf_text(value.get("content", []))
    return ""


def _jql(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def strip_sync_timestamp(body: str) -> str:
    """Drop the leading marker/timestamp line so bodies compare for substantive equality."""
    return re.sub(rf"^{re.escape(SYNC_COMMENT_MARKER)}.*$", "", body, count=1, flags=re.M).strip()


def build_sync_comment(gh_items: list[dict]) -> str:
    """Compose the terse, idempotent sync comment body for a set of linked GitHub items."""
    ts = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    ordered = sorted(
        gh_items,
        key=lambda i: (0 if i.get("state") == "open" else 1, -_iso_to_epoch(i.get("updated_at"))),
    )
    primary = ordered[0]

    linked_lines = []
    for item in ordered:
        kind = "PR" if "pull_request" in item else "Issue"
        ms = (item.get("milestone") or {}).get("title") or "-"
        linked_lines.append(
            f"- {kind} #{item['number']} {item['html_url']} "
            f"state={item.get('state')} milestone={ms} updated={item.get('updated_at', '')[:10]}"
        )

    header = (
        f"{SYNC_COMMENT_MARKER} Last synced from GitHub: {ts}\n"
        f"Primary source: {primary.get('html_url')}\n"
        f"State: {primary.get('state')}"
    )
    if primary.get("milestone"):
        header += f"  Milestone: {primary['milestone']['title']}"
    return header + "\n\nLinked GitHub items:\n" + "\n".join(linked_lines)


def _iso_to_epoch(ts: str | None) -> int:
    if not ts:
        return 0
    try:
        return int(datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp())
    except ValueError:
        return 0
