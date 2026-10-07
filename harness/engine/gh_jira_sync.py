"""Config-driven GitHub<->Jira synchronization, transposed from the proven
TTSE petrified-forest tooling. Two deliberately separate one-directional
flows avoid the split-brain oscillation of a single bidirectional sync:

  * sync_jira_from_github:  Jira <- GitHub (labels, assignee, sync comment)
  * backfill_github_from_jira:  GitHub <- Jira (assignee only, fail-closed)

Neither flow ever writes the Jira description field (see AcliJiraAdapter
module docstring for the incident that motivated this).
"""
from __future__ import annotations

from harness.adapters.acli_jira import (
    AcliJiraAdapter,
    build_sync_comment,
    find_sync_comment,
    strip_sync_timestamp,
)
from harness.adapters.github_rest import GitHubRestAdapter, pick_primary
from harness.config import map_assignee, map_labels, milestone_label


def sync_jira_from_github(
    gh_items: list[dict],
    jira: AcliJiraAdapter,
    key: str,
    cfg: dict,
    dry_run: bool,
) -> dict:
    """Compute and apply the Jira<-GitHub diff for one ticket's linked GitHub items.

    GitHub is authoritative for engineering execution: labels, milestone
    (as a label), and the status comment. Only *managed* milestone labels are
    ever removed -- labels a human set on Jira are never touched.
    """
    primary = pick_primary(gh_items)
    result: dict = {
        "key": key,
        "gh_number": primary["number"],
        "gh_url": primary.get("html_url"),
        "linked_count": len(gh_items),
        "actions": [],
        "errors": [],
    }

    if not jira.exists(key):
        result["actions"].append("skip (Jira key not found/visible)")
        return result

    status_cat = jira.status_category(key)
    if status_cat in (cfg["sync"].get("jira_skip_status_categories") or []):
        result["actions"].append(f"skip (Jira status={status_cat})")
        return result

    desired_labels: list[str] = []
    if cfg["sync"].get("sync_labels", True):
        union: set[str] = set()
        for item in gh_items:
            union.update(label["name"] for label in item.get("labels", []))
        desired_labels = map_labels(sorted(union), cfg)

    if cfg["sync"].get("sync_milestone", True):
        ms_label = milestone_label((primary.get("milestone") or {}).get("title"), cfg)
        if ms_label:
            desired_labels.append(ms_label)
    desired_labels = sorted({x for x in desired_labels if x})

    existing_labels = jira.labels(key)
    add_labels = sorted(set(desired_labels) - existing_labels) if desired_labels else []
    ms_prefix = cfg["sync"].get("milestone_label_prefix", "milestone:")
    remove_labels = []
    if cfg["sync"].get("sync_milestone", True):
        remove_labels = [
            label for label in existing_labels if label.startswith(ms_prefix) and label not in desired_labels
        ]

    assignee = None
    if cfg["sync"].get("sync_assignee", True):
        gh_assignees = [a["login"] for a in primary.get("assignees", [])]
        want = map_assignee(gh_assignees, cfg)
        if want and want != jira.current_assignee_email(key):
            assignee = want

    want_comment = False
    comment_body = ""
    if cfg["sync"].get("append_updates", True):
        comment_body = build_sync_comment(gh_items)
        existing_comment = find_sync_comment(jira.list_comments(key))
        existing_body = (existing_comment or {}).get("body") or ""
        want_comment = strip_sync_timestamp(comment_body) != strip_sync_timestamp(existing_body)

    if not (add_labels or remove_labels or assignee or want_comment):
        result["actions"].append("no changes")
        return result

    if add_labels:
        result["actions"].append(f"add labels: {add_labels}")
    if remove_labels:
        result["actions"].append(f"remove labels: {remove_labels}")
    if assignee:
        result["actions"].append(f"assignee -> {assignee}")

    if add_labels or remove_labels or assignee:
        ok, msg = jira.edit(
            key, assignee=assignee, add_labels=add_labels, remove_labels=remove_labels, dry_run=dry_run
        )
        (result["actions"] if ok else result["errors"]).append(msg)

    if want_comment:
        ok, msg = jira.upsert_sync_comment(key, comment_body, dry_run=dry_run)
        (result["actions"] if ok else result["errors"]).append(msg)

    return result


def plan_backfill_github_from_jira(
    gh_item: dict,
    jira_key: str,
    jira_index: dict[str, dict],
    email_to_login: dict[str, str],
) -> dict:
    """Decide the assignee-backfill action for one GitHub issue. Pure; never writes.

    Fail-closed: only backfills when GitHub has no assignee, the Jira ticket
    is non-Done and assigned, and the Jira assignee maps to a known GitHub
    login. Every other case is reported as a skip, never guessed at.
    """
    result = {
        "key": jira_key,
        "gh_number": gh_item["number"],
        "gh_url": gh_item.get("html_url"),
        "gh_title": gh_item.get("title", ""),
        "action": "skip",
        "reason": "",
        "login": None,
    }

    jira = jira_index.get(jira_key)
    if jira is None:
        result["reason"] = "no matching Jira ticket"
        return result
    if gh_item.get("assignees"):
        result["reason"] = "GitHub already has an assignee -- never overwritten"
        return result
    if jira["status_category"] == "Done":
        result["reason"] = "Jira status is Done -- historical, not backfilled"
        return result
    jira_email = jira["assignee_email"]
    if not jira_email:
        result["reason"] = "Jira ticket is also unassigned -- nothing to backfill"
        return result
    login = email_to_login.get(jira_email.lower())
    if not login:
        result["reason"] = (
            f"Jira assignee {jira['assignee_name']} <{jira_email}> has no GitHub login "
            "mapped in [developers] -- add one before backfilling"
        )
        return result

    result["action"] = "backfill"
    result["login"] = login
    result["reason"] = f"Jira assignee {jira['assignee_name']} <{jira_email}> -> GitHub @{login}"
    return result


def build_jira_index(issues: list[dict]) -> dict[str, dict]:
    """Index Jira search results by key -> {status_category, assignee_email, assignee_name}."""
    index: dict[str, dict] = {}
    for issue in issues:
        fields = issue.get("fields", {})
        assignee = fields.get("assignee")
        status = fields.get("status", {})
        index[issue["key"]] = {
            "status_category": (status.get("statusCategory") or {}).get("name"),
            "assignee_email": assignee.get("emailAddress") if assignee else None,
            "assignee_name": assignee.get("displayName") if assignee else None,
        }
    return index


__all__ = [
    "sync_jira_from_github",
    "plan_backfill_github_from_jira",
    "build_jira_index",
    "GitHubRestAdapter",
    "AcliJiraAdapter",
]
