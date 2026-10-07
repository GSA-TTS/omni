"""Abstract base class all provider adapters (GitHub, GitLab, Jira) implement."""
from __future__ import annotations

import json
import os
import subprocess
import time
from abc import ABC, abstractmethod
from typing import Literal

from harness.models import CanonicalIssue

# How a sync writes the source body onto the target issue.
BodyMode = Literal["replace", "append", "comment"]


class AdapterError(RuntimeError):
    """Raised when a provider CLI invocation fails or returns malformed output."""


class CliMetrics:
    """Opt-in collector for CLI invocation counts and wall-clock latency.

    Off by default (adapters hold None), so there is no overhead in normal use.
    Attach one to count N+1 patterns and compare provider latency; see
    `omni-sync bench` and `harness/testing/bench.py`.
    """

    def __init__(self) -> None:
        self.calls: list[tuple[str, float]] = []  # (argv[0..2] joined, seconds)

    def record(self, argv: list[str], seconds: float) -> None:
        self.calls.append((" ".join(argv), seconds))

    @property
    def count(self) -> int:
        return len(self.calls)

    def count_matching(self, needle: str) -> int:
        return sum(1 for label, _ in self.calls if needle in label)


class BaseIssueAdapter(ABC):
    """Common interface for wrapping a provider CLI as a canonical issue source."""

    metrics: "CliMetrics | None" = None

    @abstractmethod
    def get_issue(self, issue_id: str) -> CanonicalIssue:
        """Fetch a single issue and normalize it to a CanonicalIssue."""

    @abstractmethod
    def create_issue(self, issue: CanonicalIssue) -> str:
        """Create a new issue on the provider. Returns the created issue identifier."""

    @abstractmethod
    def update_issue(self, issue_id: str, issue: CanonicalIssue) -> None:
        """Apply canonical field changes to an existing provider issue (replace body)."""

    def add_comment(self, issue_id: str, body: str) -> None:
        """Post a comment on the issue. Override in adapters that support it."""
        raise AdapterError(f"{type(self).__name__} does not support comments")

    def create_pull_request(
        self,
        title: str,
        body: str,
        base: str,
        head: str,
        draft: bool = False,
        assignees: list[str] | None = None,
    ) -> str:
        """Open a PR/MR. Override in adapters that support it. Returns its URL."""
        raise AdapterError(f"{type(self).__name__} does not support pull requests")

    def _run_cli(
        self,
        argv: list[str],
        env_overrides: dict[str, str] | None = None,
        parse_json: bool = True,
    ) -> dict | list | str:
        """Run a provider CLI as a subprocess list (never shell=True) and parse its stdout.

        Inherits the parent environment so PATH/credential helpers keep working,
        then layers on host/token overrides specific to the target tenant.
        """
        env = {**os.environ, **(env_overrides or {})}
        started = time.perf_counter()
        try:
            result = subprocess.run(
                argv,
                env=env,
                capture_output=True,
                text=True,
                check=True,
                timeout=60,
            )
        except subprocess.CalledProcessError as exc:
            raise AdapterError(
                f"Command failed ({' '.join(argv)}): {exc.stderr.strip()}"
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise AdapterError(f"Command timed out: {' '.join(argv)}") from exc
        finally:
            if self.metrics is not None:
                self.metrics.record(argv, time.perf_counter() - started)

        stdout = result.stdout.strip()
        if not parse_json:
            return stdout
        if not stdout:
            return {}
        try:
            return json.loads(stdout)
        except json.JSONDecodeError as exc:
            raise AdapterError(f"Non-JSON output from {argv[0]}: {stdout[:200]}") from exc
