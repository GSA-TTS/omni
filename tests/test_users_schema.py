import tomllib
from pathlib import Path

import pytest

from harness.identity import UserRoster, _validate_users

_EXAMPLE = Path(__file__).resolve().parent.parent / "users.toml.example"


def test_example_roster_validates_and_loads():
    roster = UserRoster.load(_EXAMPLE)  # validate=True by default
    assert roster.username_for_target("gh-tts", "person.one@agency.gov") == "gh-login-1"


def test_valid_roster_passes():
    data = tomllib.loads(
        '[users."a@agency.gov"]\ngh = "a"\nhelix = "a_h"\ngitlab = "a_gl"\n'
    )
    _validate_users(data, _EXAMPLE)  # must not exit


def test_unknown_host_field_rejected():
    data = tomllib.loads('[users."a@agency.gov"]\ngh = "a"\nslack = "nope"\n')
    with pytest.raises(SystemExit, match="users.toml invalid"):
        _validate_users(data, _EXAMPLE)


def test_non_string_username_rejected():
    data = tomllib.loads('[users."a@agency.gov"]\ngh = 123\n')
    with pytest.raises(SystemExit, match="users.toml invalid"):
        _validate_users(data, _EXAMPLE)


def test_empty_entry_rejected():
    data = tomllib.loads('[users."a@agency.gov"]\n')
    with pytest.raises(SystemExit, match="users.toml invalid"):
        _validate_users(data, _EXAMPLE)
