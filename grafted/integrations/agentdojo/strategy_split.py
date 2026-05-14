"""Deterministic train/test split of AgentDojo injection_tasks.

Used by both the offline training script and the online evaluation runner
so that the same (suite, seed, strategy) tuple always yields exactly the
same partition of injection_task IDs. Required for honest Pattern-2
methodology: strategy library trained on the TRAIN set MUST be evaluated
on the held-out TEST set (no leakage).

Split strategies (selectable):

  strategy="alternating" (DEFAULT, recommended)
    Sort IDs by numeric suffix, then alternate: even-position → train,
    odd-position → test. Interleaves whatever difficulty ordering exists
    in the suite's injection_task numbering, so train and test both
    contain a mix of easy/hard injections. This matters for workspace
    in particular, where the sequential split (below) puts simpler
    one-shot actions (0-6) in train and harder compound actions (7-13)
    in test, leaving both attacks bottlenecked by suite difficulty
    asymmetry rather than attacker quality.

  strategy="sequential"
    Sort IDs by numeric suffix, take first ceil(n/2) → train, rest →
    test. Simpler and matches AutoInject's original convention, but
    leaks suite-internal difficulty ordering into the split.

Per-suite split sizes (identical under both strategies):
    workspace  14 → train 7, test 7
    banking     9 → train 5, test 4
    travel      7 → train 4, test 3
    slack       5 → train 3, test 2

Note: slack's IDs are 1..5 (no injection_task_0). The split still operates
on the sorted list.
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
    strategy: str = "alternating",
) -> tuple[list[str], list[str]]:
    """Return (train_injection_ids, test_injection_ids).

    Deterministic, reproducible by anyone running with the same
    (suite, seed, strategy).

    Args:
        suite: AgentDojo TaskSuite instance.
        seed: kept for API compat — does not affect output under the
            current deterministic strategies. (Future seeded-shuffle
            variant would honor it.)
        strategy: "alternating" (default) or "sequential". See module
            docstring for what each one does and when to use which.
    """
    ids = sorted_injection_ids(suite)
    n = len(ids)
    if n < 2:
        return list(ids), []
    if strategy == "alternating":
        train = ids[0::2]
        test = ids[1::2]
    elif strategy == "sequential":
        n_train = math.ceil(n / 2)
        train = ids[:n_train]
        test = ids[n_train:]
    else:
        raise ValueError(f"Unknown split strategy: {strategy!r}")
    return train, test


def get_train_test_injection_split_by_name(
    suite_name: str,
    benchmark_version: str = "v1.2",
    seed: int = 42,
    strategy: str = "alternating",
) -> tuple[list[str], list[str]]:
    """Convenience wrapper that loads the suite from AgentDojo first."""
    from agentdojo.task_suite.load_suites import get_suite

    suite = get_suite(benchmark_version, suite_name)
    return get_train_test_injection_split(suite, seed=seed, strategy=strategy)
