"""GitHub REST issue/PR enumeration used by the config-driven GitHub<->Jira
sync engine. Transposed from the TTSE petrified-forest sync tooling.

Reads via `gh api --paginate` (REST) rather than GraphQL so the project-board
GraphQL quota is untouched. Groups issues/PRs by the `<KEY>-###` reference in
their title so a single tracker ticket can gather all its linked items.
"""

from __future__ import annotations

import json
import re
import subprocess

from harness.adapters.base import AdapterError


class GitHubRestAdapter:
    """Enumerate issues/PRs for a repo and group them by issue-key reference."""

    def __init__(self, org: str, key_prefix: str = "FPDF"):
        self.org = org
        self.key_re = re.compile(rf"\b{re.escape(key_prefix)}-(\d+)\b", re.IGNORECASE)
        self.key_prefix = key_prefix

    def paginate_issues(self, repo: str, state: str = "all") -> list[dict]:
        """Fetch issues (including PRs) for one repo, flattened to one object per line."""
        try:
            result = subprocess.run(
                [
                    "gh",
                    "api",
                    "--paginate",
                    "--jq",
                    ".[]",
                    f"/repos/{self.org}/{repo}/issues?state={state}&per_page=100",
                ],
                capture_output=True,
                text=True,
                check=True,
                timeout=180,
            )
        except subprocess.CalledProcessError as exc:
            raise AdapterError(
                f"gh api failed for {self.org}/{repo}, exit {exc.returncode}"
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise AdapterError(f"gh api timed out for {self.org}/{repo}") from exc

        items: list[dict] = []
        for line in result.stdout.splitlines():
            line = line.strip()
            if line:
                items.append(json.loads(line))
        return items

    def key_in_title(self, title: str) -> str | None:
        """Return the normalized issue key (e.g. 'FPDF-395') in a title, or None."""
        match = self.key_re.search(title or "")
        return f"{self.key_prefix}-{match.group(1)}" if match else None

    def group_by_key(self, items: list[dict]) -> dict[str, list[dict]]:
        """Group issues/PRs by the issue key referenced in their title."""
        grouped: dict[str, list[dict]] = {}
        for item in items:
            key = self.key_in_title(item.get("title", ""))
            if key:
                grouped.setdefault(key, []).append(item)
        return grouped

    def add_assignee(
        self, repo: str, number: int, login: str, dry_run: bool = False
    ) -> tuple[bool, str]:
        cmd = [
            "gh",
            "issue",
            "edit",
            str(number),
            "--repo",
            f"{self.org}/{repo}",
            "--add-assignee",
            login,
        ]
        if dry_run:
            return True, f"dry-run: {' '.join(cmd)}"
        try:
            subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=30)
        except subprocess.CalledProcessError as exc:
            return (
                False,
                f"gh issue edit failed for {self.org}/{repo}, exit {exc.returncode}",
            )
        return True, f"gh: assigned {login}"


def pick_primary(gh_items: list[dict]) -> dict:
    """Choose the canonical GitHub item: any open beats any closed; newest wins within a bucket."""
    return sorted(
        gh_items,
        key=lambda i: (
            0 if i.get("state") == "open" else 1,
            -_iso_to_epoch(i.get("updated_at")),
        ),
    )[0]


def _iso_to_epoch(ts: str | None) -> int:
    from datetime import datetime

    if not ts:
        return 0
    try:
        return int(datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp())
    except ValueError:
        return 0
