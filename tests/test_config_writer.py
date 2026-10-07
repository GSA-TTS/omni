import tomllib

import pytest

from harness.config_writer import build_project_toml, build_users_toml


def test_build_project_toml_supports_all_value_shapes():
    rendered = build_project_toml(
        [
            'jira.project_key="TEST"',
            'jira.base_url="https://jira.example"',
            'github.org="example-org"',
            'github.repos=["one", "two"]',
            "github.project_number=42",
            'gitlab.host="gitlab.example"',
            'gitlab.project="group/project"',
            'board.gh_tts_url="https://github.com/o/r/issues/#TICKET#"',
            'mirror.origin="git@github.com:o/r.git"',
            "sync.sync_labels=true",
            "sync.sync_status=false",
            'sync.jira_skip_status_categories=["Done"]',
            'labels."area: api"="area-api"',
            'always_apply.jira_labels=["managed"]',
        ]
    )
    data = tomllib.loads(rendered)
    assert data["schema_version"] == 1
    assert data["github"]["repos"] == ["one", "two"]
    assert data["labels"]["area: api"] == "area-api"
    assert data["sync"]["sync_labels"] is True


def test_build_project_toml_rejects_duplicate_assignment():
    with pytest.raises(ValueError, match="duplicate assignment"):
        build_project_toml(
            [
                'jira.project_key="TEST"',
                'jira.project_key="OTHER"',
                'github.org="org"',
                'github.repos=["repo"]',
            ]
        )


def test_build_users_toml_validates_group_references():
    rendered = build_users_toml(
        ['person@agency.gov.gh="login"'],
        [
            'team.members=["person@agency.gov"]',
            'team.github_org="example-org"',
            'team.github_team="team"',
        ],
    )
    data = tomllib.loads(rendered)
    assert data["users"]["person@agency.gov"]["gh"] == "login"
    assert data["groups"]["team"]["members"] == ["person@agency.gov"]


def test_build_users_toml_rejects_unknown_group_member():
    with pytest.raises(SystemExit, match="references unknown users"):
        build_users_toml([], ['team.members=["missing@agency.gov"]'])
