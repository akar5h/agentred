"""Deterministic train/test split of AgentDojo injection_tasks.

Used by both the offline training script and the online evaluation runner
so that the same (suite, seed) pair always yields exactly the same
partition of injection_task IDs. Required for honest Pattern-2
methodology: strategy library trained on the TRAIN set MUST be evaluated
on the held-out TEST set (no leakage).

Split policy:
- Sort injection_task IDs by their numeric suffix (some suites register
  IDs out of insertion order, e.g. travel's IDs are [6, 0, 1, 2, 3, 4, 5])
- First ceil(n/2) → train; remaining → test
- seed is accepted for forward-compat with a seeded-shuffle variant but
  the default is deterministic-by-suffix (no shuffle)

Per-suite split sizes (default, n_inj from AgentDojo v1.2):
    workspace  14 → train 7, test 7
    banking     9 → train 5, test 4
    travel      7 → train 4, test 3
    slack       5 → train 3, test 2

Note: slack's IDs are 1..5 (no injection_task_0). The split still operates
on the sorted list so train = [1, 2, 3], test = [4, 5].
"""
from __future__ import annotations

import math
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agentdojo.task_suite.task_suite import TaskSuite

# Hardcoded sizes are NOT the source of truth — we always read from the
# suite at call time. This table is for documentation + smoke checks.
EXPECTED_SIZES = {
    "workspace": 14,
    "banking": 9,
    "travel": 7,
    "slack": 5,
}


_SUFFIX_RE = re.compile(r"injection_task_(\d+)")


def _suffix(injection_id: str) -> int:
    m = _SUFFIX_RE.match(injection_id)
    if not m:
        raise ValueError(f"injection_task id does not match expected pattern: {injection_id!r}")
    return int(m.group(1))


def sorted_injection_ids(suite: "TaskSuite") -> list[str]:
    """Return suite.injection_tasks keys sorted by numeric suffix."""
    return sorted(suite.injection_tasks.keys(), key=_suffix)


def get_train_test_injection_split(
    suite: "TaskSuite",
    seed: int = 42,
) -> tuple[list[str], list[str]]:
    """Return (train_injection_ids, test_injection_ids).

    Deterministic, reproducible by anyone running with the same seed.
    Default policy: take first ceil(n/2) of sorted IDs as train.
    """
    ids = sorted_injection_ids(suite)
    n = len(ids)
    if n < 2:
        # Degenerate but defined: 1 id → train=[id], test=[]
        return list(ids), []
    n_train = math.ceil(n / 2)
    train = ids[:n_train]
    test = ids[n_train:]
    return train, test


def get_train_test_injection_split_by_name(
    suite_name: str,
    benchmark_version: str = "v1.2",
    seed: int = 42,
) -> tuple[list[str], list[str]]:
    """Convenience wrapper that loads the suite from AgentDojo first."""
    from agentdojo.task_suite.load_suites import get_suite

    suite = get_suite(benchmark_version, suite_name)
    return get_train_test_injection_split(suite, seed=seed)
