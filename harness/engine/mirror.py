"""Git mirroring: push the current repository's code to one or more remotes
(github.com, GitHub Enterprise Server, GitLab) in a single invocation.

Remotes are resolved from the [mirror] table of sync_config.toml. This wraps
`git remote`/`git push` as subprocess list calls (never shell=True) and
reports per-remote results so one unreachable remote does not abort the rest.
"""
from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass


@dataclass
class MirrorResult:
    remote: str
    url: str
    ok: bool
    message: str


class GitMirror:
    """Push a ref to a set of named remotes defined in config.

    Auth is transport-agnostic: an HTTPS remote uses git's credential helper
    (e.g. the `gh` web session), an SSH remote uses the agent/keychain or an
    interactive passphrase. The mirror logic does not care which. Set
    batch=True only for unattended runs where blocking on a passphrase prompt
    is undesirable.
    """

    def __init__(self, remotes: dict[str, str], cwd: str | None = None, batch: bool = False):
        self.remotes = remotes
        self.cwd = cwd
        self.batch = batch

    def _run(self, argv: list[str]) -> tuple[int, str]:
        env = dict(os.environ)
        if self.batch and "GIT_SSH_COMMAND" not in env:
            # Opt-in: make SSH fail fast instead of blocking on a passphrase
            # prompt. Off by default so interactive SSH/web auth still works.
            env["GIT_SSH_COMMAND"] = "ssh -o BatchMode=yes"
        try:
            r = subprocess.run(argv, capture_output=True, text=True, timeout=120, cwd=self.cwd, env=env)
            return r.returncode, (r.stdout + r.stderr).strip()
        except (OSError, subprocess.TimeoutExpired) as exc:
            return 1, str(exc)

    def _ensure_remote(self, name: str, url: str) -> None:
        """Add the remote if absent, or update its URL if it already exists."""
        rc, _ = self._run(["git", "remote", "get-url", name])
        if rc == 0:
            self._run(["git", "remote", "set-url", name, url])
        else:
            self._run(["git", "remote", "add", name, url])

    def push(self, ref: str, targets: list[str], dry_run: bool = False) -> list[MirrorResult]:
        """Push `ref` to each named target. Unknown targets are reported, not fatal."""
        results: list[MirrorResult] = []
        for name in targets:
            url = self.remotes.get(name)
            if not url:
                results.append(MirrorResult(name, "", False, f"no remote '{name}' in [mirror] config"))
                continue

            if dry_run:
                results.append(MirrorResult(name, url, True, f"dry-run: git push {name} {ref}"))
                continue

            self._ensure_remote(name, url)
            rc, out = self._run(["git", "push", name, ref])
            results.append(MirrorResult(name, url, rc == 0, out.splitlines()[-1] if out else "pushed"))
        return results
