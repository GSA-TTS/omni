"""Git mirroring: push the current repository's code to one or more remotes
(github.com, GitHub Enterprise Server, GitLab) in a single invocation.

Remotes are resolved from the [mirror] table of omni-project.toml. This wraps
`git remote`/`git push` as subprocess list calls (never shell=True) and
reports per-remote results so one unreachable remote does not abort the rest.
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from urllib.parse import urlsplit


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

    def __init__(
        self, remotes: dict[str, str], cwd: str | None = None, batch: bool = False
    ):
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
            r = subprocess.run(
                argv, capture_output=True, text=True, timeout=120, cwd=self.cwd, env=env
            )
            return r.returncode, (r.stdout + r.stderr).strip()
        except (OSError, subprocess.TimeoutExpired) as exc:
            return 1, str(exc)

    def _resolve_commit(self, ref: str) -> tuple[bool, str]:
        rc, output = self._run(
            ["git", "rev-parse", "--verify", "--end-of-options", f"{ref}^{{commit}}"]
        )
        return rc == 0, output.splitlines()[-1] if output else ""

    def _remote_head(self, url: str, destination: str) -> tuple[bool, str]:
        rc, output = self._run(
            ["git", "ls-remote", "--heads", "--", url, f"refs/heads/{destination}"]
        )
        if rc != 0:
            return False, output or "remote is unreachable"
        return True, output.split()[0] if output else ""

    @staticmethod
    def _safe_url(url: str) -> bool:
        """Reject credentials embedded in scheme-based remote URLs."""
        parsed = urlsplit(url)
        if parsed.scheme in {"http", "https"}:
            return parsed.username is None and parsed.password is None
        return parsed.password is None

    def push(
        self,
        source_ref: str,
        destination: str,
        targets: list[str],
        dry_run: bool = False,
        allow_non_head: bool = False,
        allow_existing: bool = False,
    ) -> list[MirrorResult]:
        """Push one resolved commit to an explicit destination branch."""
        results: list[MirrorResult] = []
        destination_rc, _ = self._run(
            ["git", "check-ref-format", "--branch", destination]
        )
        if destination_rc != 0:
            return [
                MirrorResult(
                    name,
                    self.remotes.get(name, ""),
                    False,
                    f"invalid destination branch {destination!r}",
                )
                for name in targets
            ]
        source_ok, source_sha = self._resolve_commit(source_ref)
        head_ok, head_sha = self._resolve_commit("HEAD")
        if not source_ok or not head_ok:
            message = f"cannot resolve source ref {source_ref!r} or HEAD"
            return [
                MirrorResult(name, self.remotes.get(name, ""), False, message)
                for name in targets
            ]
        if source_sha != head_sha and not allow_non_head:
            message = (
                f"source {source_ref} resolves to {source_sha}, but checked-out HEAD is "
                f"{head_sha}; use --allow-non-head only after verifying provenance"
            )
            return [
                MirrorResult(name, self.remotes.get(name, ""), False, message)
                for name in targets
            ]

        rc, integrity = self._run(
            ["git", "fsck", "--connectivity-only", "--no-dangling"]
        )
        if rc != 0:
            return [
                MirrorResult(
                    name,
                    self.remotes.get(name, ""),
                    False,
                    f"source object-integrity check failed: {integrity}",
                )
                for name in targets
            ]

        for name in targets:
            url = self.remotes.get(name)
            if not url:
                results.append(
                    MirrorResult(
                        name, "", False, f"no remote '{name}' in [mirror] config"
                    )
                )
                continue
            if not self._safe_url(url):
                results.append(
                    MirrorResult(
                        name,
                        "",
                        False,
                        "remote URL must not contain embedded credentials",
                    )
                )
                continue

            remote_ok, remote_sha = self._remote_head(url, destination)
            if not remote_ok:
                results.append(MirrorResult(name, url, False, remote_sha))
                continue
            if remote_sha == source_sha:
                results.append(
                    MirrorResult(
                        name,
                        url,
                        True,
                        f"already synchronized at {source_sha} on {destination}",
                    )
                )
                continue
            if remote_sha and not allow_existing:
                results.append(
                    MirrorResult(
                        name,
                        url,
                        False,
                        f"destination {destination} already exists at {remote_sha}; "
                        "use a review branch or --allow-existing after comparing histories",
                    )
                )
                continue

            refspec = f"{source_sha}:refs/heads/{destination}"
            if dry_run:
                state = f"existing {remote_sha}" if remote_sha else "new branch"
                results.append(
                    MirrorResult(
                        name,
                        url,
                        True,
                        f"dry-run: git push {url} {refspec} ({state})",
                    )
                )
                continue

            rc, out = self._run(["git", "push", "--", url, refspec])
            results.append(
                MirrorResult(
                    name, url, rc == 0, out.splitlines()[-1] if out else "pushed"
                )
            )
        return results
