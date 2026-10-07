from pathlib import Path

from harness.identity import HOST_URLS, IdentityMap

_MAP = IdentityMap(
    {
        "https://github.helix.gsa.gov/": {"person.one@agency.gov": "johnhjediny"},
        "https://github.com/GSA-TTS": {"person.one@agency.gov": "jjediny"},
        "https://workshop.cloud.gov/": {"person.one@agency.gov": "john.jediny"},
    }
)


def test_username_for_target_per_host():
    assert _MAP.username_for_target("gh-helix", "person.one@agency.gov") == "johnhjediny"
    assert _MAP.username_for_target("gh-tts", "person.one@agency.gov") == "jjediny"
    assert _MAP.username_for_target("gl-cg", "person.one@agency.gov") == "john.jediny"


def test_lookup_is_case_insensitive_on_email():
    assert _MAP.username_for_target("gh-tts", "John.Jediny@GSA.gov") == "jjediny"


def test_unmapped_email_returns_none():
    assert _MAP.username_for_target("gh-tts", "nobody@gsa.gov") is None


def test_reverse_lookup():
    url = HOST_URLS["gh-helix"]
    assert _MAP.email_for_username(url, "johnhjediny") == "person.one@agency.gov"


def test_translate_across_hosts():
    # Helix username -> github.com username for the same person.
    assert _MAP.translate(HOST_URLS["gh-helix"], HOST_URLS["gh-tts"], "johnhjediny") == "jjediny"


def test_resolve_assignee_email_maps():
    assert _MAP.resolve_assignee("gh-tts", "person.one@agency.gov") == "jjediny"


def test_resolve_assignee_username_passthrough():
    assert _MAP.resolve_assignee("gh-tts", "someuser") == "someuser"


def test_resolve_assignee_unmapped_email_is_none():
    assert _MAP.resolve_assignee("gh-tts", "nobody@gsa.gov") is None


def test_load_reads_project_identity_map():
    path = Path(__file__).resolve().parent.parent / "identity_map.toml"
    loaded = IdentityMap.load(path)
    assert loaded.username_for_target("gh-helix", "person.one@agency.gov") == "johnhjediny"


def test_load_missing_file_is_empty():
    loaded = IdentityMap.load(Path("/nonexistent/identity_map.toml"))
    assert loaded.username_for_target("gh-tts", "person.one@agency.gov") is None
