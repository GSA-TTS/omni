import tomllib

import pytest

from harness.config import validate_config
from harness.resources import resource_text

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


def test_project_schema_is_available_as_runtime_resource():
    schema = resource_text("schema/omni-project.schema.json")
    assert '"schema_version"' in schema


def test_board_urls_must_be_absolute_and_end_with_slash():
    valid = _cfg(
        _VALID + '\n[board]\ngh_tts_url = "https://github.com/o/r/issues/#TICKET#"\n'
    )
    validate_config(valid)
    invalid = _cfg(
        _VALID + '\n[board]\ngh_tts_url = "https://github.com/o/r/issues/"\n'
    )
    with pytest.raises(SystemExit, match="does not match"):
        validate_config(invalid)
    insecure = _cfg(
        _VALID + '\n[board]\ngh_tts_url = "http://github.com/o/r/issues/#TICKET#"\n'
    )
    with pytest.raises(SystemExit, match="does not match"):
        validate_config(insecure)


def test_unsupported_schema_version_exits():
    with pytest.raises(SystemExit, match="schema_version"):
        validate_config(
            _cfg(_VALID.replace("schema_version = 1", "schema_version = 99"))
        )


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


def test_gitlab_host_and_project_are_supported():
    cfg = _cfg(
        _VALID + '\n[gitlab]\nhost = "gitlab.example"\nproject = "group/project"\n'
    )
    validate_config(cfg)


def test_obsolete_gitlab_project_key_is_rejected():
    cfg = _cfg(_VALID + '\n[gitlab]\nproject_key = "LEGACY"\n')
    with pytest.raises(SystemExit, match="Additional properties"):
        validate_config(cfg)
