"""Abstract base class all provider adapters (GitHub, GitLab, Jira) implement."""
from __future__ import annotations

import json
import os
import subprocess
from abc import ABC, abstractmethod

from harness.models import CanonicalIssue


class AdapterError(RuntimeError):
    """Raised when a provider CLI invocation fails or returns malformed output."""


class BaseIssueAdapter(ABC):
    """Common interface for wrapping a provider CLI as a canonical issue source."""

    @abstractmethod
    def get_issue(self, issue_id: str) -> CanonicalIssue:
        """Fetch a single issue and normalize it to a CanonicalIssue."""

    @abstractmethod
    def create_issue(self, issue: CanonicalIssue) -> str:
        """Create a new issue on the provider. Returns the created issue identifier."""

    @abstractmethod
    def update_issue(self, issue_id: str, issue: CanonicalIssue) -> None:
        """Apply canonical field changes to an existing provider issue."""

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

        stdout = result.stdout.strip()
        if not parse_json:
            return stdout
        if not stdout:
            return {}
        try:
            return json.loads(stdout)
        except json.JSONDecodeError as exc:
            raise AdapterError(f"Non-JSON output from {argv[0]}: {stdout[:200]}") from exc
