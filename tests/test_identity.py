from pathlib import Path

from harness.identity import UserRoster

# Placeholder identities only -- real team data lives in gitignored
# users.toml, never in the repo (phishing concern).
_ROSTER = UserRoster(
    {
        "dev.user@agency.gov": {
            "gh": "gh-login",
            "helix": "ghes-login",
            "gitlab": "gitlab-login",
        }
    }
)


def test_username_for_target_per_host():
    assert _ROSTER.username_for_target("gh-helix", "dev.user@agency.gov") == "ghes-login"
    assert _ROSTER.username_for_target("gh-tts", "dev.user@agency.gov") == "gh-login"
    assert _ROSTER.username_for_target("gl-cg", "dev.user@agency.gov") == "gitlab-login"


def test_lookup_is_case_insensitive_on_email():
    assert _ROSTER.username_for_target("gh-tts", "Dev.User@AGENCY.gov") == "gh-login"


def test_unmapped_email_returns_none():
    assert _ROSTER.username_for_target("gh-tts", "nobody@agency.gov") is None


def test_reverse_lookup():
    assert _ROSTER.email_for_username("gh-helix", "ghes-login") == "dev.user@agency.gov"


def test_translate_across_hosts():
    # Helix username -> github.com username for the same person.
    assert _ROSTER.translate("gh-helix", "gh-tts", "ghes-login") == "gh-login"


def test_resolve_assignee_email_maps():
    assert _ROSTER.resolve_assignee("gh-tts", "dev.user@agency.gov") == "gh-login"


def test_resolve_assignee_username_passthrough():
    assert _ROSTER.resolve_assignee("gh-tts", "someuser") == "someuser"


def test_resolve_assignee_unmapped_email_is_none():
    assert _ROSTER.resolve_assignee("gh-tts", "nobody@agency.gov") is None


def test_resolve_issue_user_keeps_current_identity_and_jira_email():
    assert _ROSTER.resolve_issue_user("gh-tts", "@me") == "@me"
    assert _ROSTER.resolve_issue_user("jira-mod", "dev.user@agency.gov") == "dev.user@agency.gov"


def test_resolve_issue_user_maps_email_for_host():
    assert _ROSTER.resolve_issue_user("gh-helix", "dev.user@agency.gov") == "ghes-login"


def test_github_login_to_jira_email_covers_both_hosts():
    mapping = _ROSTER.github_login_to_jira_email()
    assert mapping["gh-login"] == "dev.user@agency.gov"
    assert mapping["ghes-login"] == "dev.user@agency.gov"


def test_load_reads_example_roster():
    # The committed template uses placeholders; the real file is gitignored.
    path = Path(__file__).resolve().parent.parent / "users.toml.example"
    loaded = UserRoster.load(path)
    assert loaded.username_for_target("gh-tts", "person.one@agency.gov") == "gh-login-1"


def test_load_missing_file_is_empty():
    loaded = UserRoster.load(Path("/nonexistent/users.toml"))
    assert loaded.username_for_target("gh-tts", "person.one@agency.gov") is None
