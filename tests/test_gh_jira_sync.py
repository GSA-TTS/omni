import tomllib

from harness.engine.gh_jira_sync import (
    build_jira_index,
    plan_backfill_github_from_jira,
    sync_jira_from_github,
)

_CFG = tomllib.loads(
    """
schema_version = 1
[jira]
project_key = "FPDF"
acli_bin = "acli"
[github]
org = "GSA-TTS"
repos = ["r1"]
[sync]
sync_labels = true
sync_assignee = true
sync_milestone = true
append_updates = true
milestone_label_prefix = "milestone:"
jira_skip_status_categories = ["Done"]
[developers]
devuser = "dev.user@agency.gov"
[labels]
"bug" = "bug"
[always_apply]
jira_labels = ["github-sync"]
"""
)


class FakeJira:
    def __init__(self, status="In Progress", labels=None, assignee=None, comments=None):
        self._status = status
        self._labels = set(labels or [])
        self._assignee = assignee
        self._comments = comments or []
        self.edits: list[dict] = []
        self.comment_writes: list[str] = []

    def exists(self, key):
        return True

    def status_category(self, key):
        return self._status

    def labels(self, key):
        return set(self._labels)

    def current_assignee_email(self, key):
        return self._assignee

    def list_comments(self, key):
        return self._comments

    def edit(
        self, key, *, assignee=None, add_labels=None, remove_labels=None, dry_run=False
    ):
        self.edits.append(
            {
                "assignee": assignee,
                "add": add_labels,
                "remove": remove_labels,
                "dry_run": dry_run,
            }
        )
        return True, "updated"

    def upsert_sync_comment(self, key, body, *, dry_run=False):
        self.comment_writes.append(body)
        return True, "comment updated"


def _gh_item(number=1, state="open", labels=None, assignees=None, milestone=None):
    return {
        "number": number,
        "state": state,
        "html_url": f"https://github.com/x/y/issues/{number}",
        "updated_at": "2026-01-01T00:00:00Z",
        "labels": [{"name": n} for n in (labels or [])],
        "assignees": [{"login": a} for a in (assignees or [])],
        "milestone": {"title": milestone} if milestone else None,
    }


def test_skips_done_jira_tickets():
    jira = FakeJira(status="Done")
    result = sync_jira_from_github([_gh_item()], jira, "FPDF-1", _CFG, dry_run=False)
    assert any("skip" in a for a in result["actions"])
    assert jira.edits == []


def test_adds_mapped_and_milestone_labels():
    jira = FakeJira(labels=set())
    sync_jira_from_github(
        [_gh_item(labels=["bug"], milestone="PI 6 Iteration 6.1")],
        jira,
        "FPDF-1",
        _CFG,
        dry_run=False,
    )
    added = jira.edits[0]["add"]
    assert "bug" in added
    assert "github-sync" in added
    assert "milestone:PI-6-Iteration-6.1" in added


def test_removes_only_stale_managed_milestone_labels():
    jira = FakeJira(labels={"milestone:OLD", "human-label", "bug", "github-sync"})
    sync_jira_from_github(
        [_gh_item(labels=["bug"])], jira, "FPDF-1", _CFG, dry_run=False
    )
    removed = jira.edits[0]["remove"]
    assert "milestone:OLD" in removed
    assert "human-label" not in removed


def test_disabled_milestone_sync_preserves_existing_milestone_labels():
    cfg = {
        **_CFG,
        "sync": {**_CFG["sync"], "sync_milestone": False, "append_updates": False},
    }
    jira = FakeJira(labels={"milestone:OLD", "bug", "github-sync"})
    result = sync_jira_from_github(
        [_gh_item(labels=["bug"])], jira, "FPDF-1", cfg, dry_run=False
    )
    assert result["actions"] == ["no changes"]
    assert jira.edits == []


def test_assignee_mapped_from_github_login():
    jira = FakeJira(labels={"bug", "github-sync"}, assignee=None)
    sync_jira_from_github(
        [_gh_item(labels=["bug"], assignees=["devuser"])],
        jira,
        "FPDF-1",
        _CFG,
        dry_run=False,
    )
    assert jira.edits[0]["assignee"] == "dev.user@agency.gov"


def test_no_changes_when_already_in_sync():
    jira = FakeJira(labels={"bug", "github-sync"})
    sync_jira_from_github(
        [_gh_item(labels=["bug"])], jira, "FPDF-1", _CFG, dry_run=False
    )
    # Labels already present -> no label edit should be issued.
    assert all(e["add"] in (None, []) for e in jira.edits)


class TestBackfill:
    def _index(self, status="In Progress", email="dev.user@agency.gov"):
        return build_jira_index(
            [
                {
                    "key": "FPDF-1",
                    "fields": {
                        "status": {"statusCategory": {"name": status}},
                        "assignee": {"emailAddress": email, "displayName": "J J"}
                        if email
                        else None,
                    },
                }
            ]
        )

    def test_backfills_when_github_unassigned(self):
        plan = plan_backfill_github_from_jira(
            _gh_item(assignees=[]),
            "FPDF-1",
            self._index(),
            {"dev.user@agency.gov": "devuser"},
        )
        assert plan["action"] == "backfill"
        assert plan["login"] == "devuser"

    def test_skips_when_github_already_assigned(self):
        plan = plan_backfill_github_from_jira(
            _gh_item(assignees=["someone"]),
            "FPDF-1",
            self._index(),
            {"dev.user@agency.gov": "devuser"},
        )
        assert plan["action"] == "skip"
        assert "already has an assignee" in plan["reason"]

    def test_skips_done_jira(self):
        plan = plan_backfill_github_from_jira(
            _gh_item(assignees=[]),
            "FPDF-1",
            self._index(status="Done"),
            {"dev.user@agency.gov": "devuser"},
        )
        assert plan["action"] == "skip"

    def test_skips_unmapped_jira_assignee(self):
        plan = plan_backfill_github_from_jira(
            _gh_item(assignees=[]),
            "FPDF-1",
            self._index(email="unknown@agency.gov"),
            {"dev.user@agency.gov": "devuser"},
        )
        assert plan["action"] == "skip"
        assert "no GitHub login" in plan["reason"]
