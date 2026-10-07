"""Benchmarking harness: measure CLI invocation counts and latency per adapter
operation. Supports an offline mode (fake runner, deterministic call counts)
for CI regression guards, and a live mode for real latency figures.

The headline guard this exists to protect: the acli Jira adapter must make
exactly ONE `workitem view` call per key (it previously made 4; see
skills/omni-sync/known-failures.md and the AcliJiraAdapter view cache).
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field


@dataclass
class OpMetric:
    provider: str
    operation: str
    calls: int
    latencies: list[float] = field(default_factory=list)

    @property
    def p50(self) -> float:
        return statistics.median(self.latencies) if self.latencies else 0.0

    @property
    def p95(self) -> float:
        if not self.latencies:
            return 0.0
        ordered = sorted(self.latencies)
        idx = min(len(ordered) - 1, int(round(0.95 * (len(ordered) - 1))))
        return ordered[idx]


def render_matrix(metrics: list[OpMetric]) -> str:
    """Render a provider × operation matrix of call counts and latency."""
    header = (
        f"{'provider':<16}{'operation':<16}{'calls':>6}{'p50(ms)':>10}{'p95(ms)':>10}"
    )
    lines = [header, "-" * len(header)]
    for m in metrics:
        lines.append(
            f"{m.provider:<16}{m.operation:<16}{m.calls:>6}"
            f"{m.p50 * 1000:>10.1f}{m.p95 * 1000:>10.1f}"
        )
    return "\n".join(lines)
