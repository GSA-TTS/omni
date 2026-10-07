import json
import subprocess

import pytest

from harness.adapters.acli_jira import (
    AcliJiraAdapter,
    build_sync_comment,
    find_sync_comment,
    strip_sync_timestamp,
)
from harness.adapters.base import AdapterError


def _mock_completed(stdout: str) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=[], returncode=0, stdout=stdout, stderr="")


_WORKITEM = {
    "fields": {
        "summary": "Migrate core auth service",
        "status": {"statusCategory": {"name": "In Progress"}},
        "assignee": {"emailAddress": "dev.user@agency.gov", "displayName": "Dev User"},
        "labels": ["bug", "milestone:PI-6-Iteration-6.1"],
    }
}


class TestAcliJiraAdapter:
    def test_get_issue_never_requests_description(self, mocker):
        run_mock = mocker.patch("subprocess.run", return_value=_mock_completed(json.dumps(_WORKITEM)))
        adapter = AcliJiraAdapter("acli", "FPDF")
        issue = adapter.get_issue("FPDF-402")

        assert issue.title == "Migrate core auth service"
        assert issue.status == "OPEN"
        assert issue.body_markdown == ""
        fields_arg = run_mock.call_args.args[0]
        assert "description" not in " ".join(fields_arg)

    def test_done_status_category_maps_to_closed(self, mocker):
        done = {"fields": {**_WORKITEM["fields"], "status": {"statusCategory": {"name": "Done"}}}}
        mocker.patch("subprocess.run", return_value=_mock_completed(json.dumps(done)))
        adapter = AcliJiraAdapter("acli", "FPDF")
        assert adapter.get_issue("FPDF-402").status == "CLOSED"

    def test_edit_never_includes_description_flag(self, mocker):
        run_mock = mocker.patch("subprocess.run", return_value=_mock_completed(""))
        adapter = AcliJiraAdapter("acli", "FPDF")
        ok, _ = adapter.edit("FPDF-402", assignee="dev.user@agency.gov", add_labels=["bug"])

        assert ok
        argv = run_mock.call_args.args[0]
        assert "--description" not in argv
        assert "--assignee" in argv and "--labels" in argv

    def test_edit_no_op_when_nothing_to_change(self, mocker):
        run_mock = mocker.patch("subprocess.run")
        adapter = AcliJiraAdapter("acli", "FPDF")
        ok, msg = adapter.edit("FPDF-402")
        assert ok and msg == "no-op"
        run_mock.assert_not_called()

    def test_edit_dry_run_does_not_execute(self, mocker):
        run_mock = mocker.patch("subprocess.run")
        adapter = AcliJiraAdapter("acli", "FPDF")
        ok, msg = adapter.edit("FPDF-402", add_labels=["bug"], dry_run=True)
        assert ok and msg.startswith("dry-run:")
        run_mock.assert_not_called()

    def test_upsert_sync_comment_updates_existing_in_place(self, mocker):
        comments = {"comments": [{"id": "99", "body": "[github-sync] old"}]}
        run_mock = mocker.patch(
            "subprocess.run",
            side_effect=[_mock_completed(json.dumps(comments)), _mock_completed("")],
        )
        adapter = AcliJiraAdapter("acli", "FPDF")
        ok, msg = adapter.upsert_sync_comment("FPDF-402", "[github-sync] new")

        assert ok and msg == "comment updated"
        update_argv = run_mock.call_args_list[1].args[0]
        assert "update" in update_argv and "--id" in update_argv

    def test_upsert_sync_comment_creates_when_absent(self, mocker):
        comments = {"comments": [{"id": "1", "body": "a human comment"}]}
        run_mock = mocker.patch(
            "subprocess.run",
            side_effect=[_mock_completed(json.dumps(comments)), _mock_completed("")],
        )
        adapter = AcliJiraAdapter("acli", "FPDF")
        ok, msg = adapter.upsert_sync_comment("FPDF-402", "[github-sync] new")

        assert ok and msg == "comment created"
        create_argv = run_mock.call_args_list[1].args[0]
        assert "create" in create_argv

    def test_list_comments_fails_closed_on_cli_error(self, mocker):
        mocker.patch(
            "subprocess.run",
            side_effect=subprocess.CalledProcessError(1, ["acli"], stderr="unauthorized"),
        )
        adapter = AcliJiraAdapter("acli", "FPDF")
        with pytest.raises(AdapterError, match="Command failed"):
            adapter.list_comments("FPDF-402")

    def test_list_comments_rejects_malformed_response(self, mocker):
        mocker.patch("subprocess.run", return_value=_mock_completed("{}"))
        adapter = AcliJiraAdapter("acli", "FPDF")
        with pytest.raises(AdapterError, match="Invalid comment list response"):
            adapter.list_comments("FPDF-402")


class TestSyncComment:
    def test_find_sync_comment_matches_marker_not_author(self):
        comments = [
            {"id": "1", "body": "normal comment mentioning github"},
            {"id": "2", "body": "[github-sync] Last synced..."},
        ]
        found = find_sync_comment(comments)
        assert found["id"] == "2"

    def test_find_sync_comment_returns_none_when_absent(self):
        assert find_sync_comment([{"id": "1", "body": "nope"}]) is None

    def test_find_sync_comment_rejects_duplicate_markers(self):
        comments = [
            {"id": "1", "body": "[github-sync] first"},
            {"id": "2", "body": "[github-sync] second"},
        ]
        with pytest.raises(AdapterError, match="Multiple managed Jira sync comments"):
            find_sync_comment(comments)

    def test_strip_sync_timestamp_removes_marker_line(self):
        body = "[github-sync] Last synced from GitHub: 2026-01-01T00:00:00Z\nState: open"
        assert strip_sync_timestamp(body) == "State: open"

    def test_build_sync_comment_lists_items_primary_first(self):
        items = [
            {"number": 2, "state": "closed", "html_url": "u2", "updated_at": "2026-01-01T00:00:00Z"},
            {"number": 1, "state": "open", "html_url": "u1", "updated_at": "2026-02-01T00:00:00Z"},
        ]
        body = build_sync_comment(items)
        assert body.startswith("[github-sync]")
        assert "Primary source: u1" in body
        assert body.index("#1") < body.index("#2")
