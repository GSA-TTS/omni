import subprocess

import pytest

from harness.adapters.base import AdapterError
from harness.adapters.github_rest import GitHubRestAdapter


def test_paginate_failure_does_not_expose_stderr(mocker):
    secret = "sensitive provider response"
    mocker.patch(
        "subprocess.run",
        side_effect=subprocess.CalledProcessError(3, ["gh"], stderr=secret),
    )
    adapter = GitHubRestAdapter("example-org")
    with pytest.raises(AdapterError) as raised:
        adapter.paginate_issues("example-repo")
    assert str(raised.value) == "gh api failed for example-org/example-repo, exit 3"
    assert secret not in str(raised.value)


def test_assignee_failure_does_not_expose_stderr(mocker):
    secret = "sensitive provider response"
    mocker.patch(
        "subprocess.run",
        side_effect=subprocess.CalledProcessError(4, ["gh"], stderr=secret),
    )
    adapter = GitHubRestAdapter("example-org")
    ok, message = adapter.add_assignee("example-repo", 1, "example-user")
    assert not ok
    assert message == "gh issue edit failed for example-org/example-repo, exit 4"
    assert secret not in message
