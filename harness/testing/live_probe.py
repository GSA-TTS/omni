"""Live edge-case probe: create one issue per markdown edge case on a target,
read it back, and record whether the body survived the CLI round-trip intact.

This is a MANUAL tool (not part of the pytest suite) because it mutates real
issues. It drives the actual gh/glab/acli adapters so the results reflect real
provider + shell behavior, which is then curated into skills/.

Usage:
    uv run python -m harness.testing.live_probe gh-helix <owner>/<repo>
    uv run python -m harness.testing.live_probe gl-cg <group>/<project>
"""
from __future__ import annotations

import sys

from harness.adapters.github import GitHubAdapter
from harness.adapters.gitlab import GitLabAdapter
from harness.models import CanonicalIssue, strip_anchor
from harness.testing.edge_cases import EDGE_CASES

_BUILDERS = {
    "gh-tts": lambda repo: GitHubAdapter("github.com", repo),
    "gh-helix": lambda repo: GitHubAdapter("github.helix.gsa.gov", repo),
    "gl-cg": lambda repo: GitLabAdapter("workshop.cloud.gov", repo),
}


def run(target: str, repo: str) -> int:
    if target not in _BUILDERS:
        print(f"unknown target {target}; valid: {', '.join(_BUILDERS)}", file=sys.stderr)
        return 2
    adapter = _BUILDERS[target](repo)

    print(f"id\tresult\tnote")
    for case in EDGE_CASES:
        issue = CanonicalIssue.create_new(f"[omni-probe] {case.id}", case.body)
        try:
            remote = adapter.create_issue(issue)
            number = remote.rstrip("/").split("/")[-1]
            fetched = adapter.get_issue(number)
            got = strip_anchor(fetched.body_markdown)
            want = strip_anchor(case.body)
            verdict = "OK" if got == want else "DRIFT"
        except Exception as exc:  # noqa: BLE001 — probe records failures, never aborts
            verdict = "ERROR"
            remote = str(exc)[:80]
        print(f"{case.id}\t{verdict}\t{case.note} :: {remote}")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(__doc__)
        raise SystemExit(2)
    raise SystemExit(run(sys.argv[1], sys.argv[2]))
