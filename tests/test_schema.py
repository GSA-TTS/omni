import tomllib

import pytest

from harness.config import validate_config

_VALID = """
schema_version = 1
[jira]
project_key = "FPDF"
[github]
org = "GSA-TTS"
repos = ["r1"]
"""


def _cfg(text: str) -> dict:
    return tomllib.loads(text)


def test_valid_config_passes():
    validate_config(_cfg(_VALID))  # must not raise/exit


def test_committed_project_config_validates():
    from pathlib import Path

    path = Path(__file__).resolve().parent.parent / "omni-project.toml"
    validate_config(_cfg(path.read_text()), source=path)


def test_unsupported_schema_version_exits():
    with pytest.raises(SystemExit, match="schema_version"):
        validate_config(_cfg(_VALID.replace("schema_version = 1", "schema_version = 99")))


def test_missing_schema_version_exits():
    with pytest.raises(SystemExit, match="schema_version"):
        validate_config(_cfg(_VALID.replace("schema_version = 1\n", "")))


def test_missing_jira_project_key_exits():
    bad = """
schema_version = 1
[jira]
base_url = "https://example"
[github]
org = "o"
repos = ["r"]
"""
    with pytest.raises(SystemExit):
        validate_config(_cfg(bad))


def test_empty_repos_exits():
    bad = """
schema_version = 1
[jira]
project_key = "X"
[github]
org = "o"
repos = []
"""
    with pytest.raises(SystemExit):
        validate_config(_cfg(bad))
