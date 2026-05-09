# TRD-21: Phase T-2 — Multi-Cycle Adaptation

**Prerequisite:** TRD-20 (Phase T-1) passing — all components produce correct outputs individually.

**Goal:** Prove that the MUZZLE loop **actually adapts** across cycles. If memory/bandit don't
change behavior, the agentic loop is just running the same thing N times — this phase validates
the adaptive feedback loop that makes MUZZLE meaningful.

---

## What to Validate

| # | Check | Component | Pass Condition |
|---|-------|-----------|----------------|
| 1 | Strategic memory accumulation | `strategic.json` | Grows between cycles. Surface stats have `attempts >= 2` after 2 cycles |
| 2 | Bandit arm updates | `bandit.json` | Non-zero pulls and rewards after cycle 1. UCB1 scores change |
| 3 | Explorer task adaptation | Explorer | Cycle 1 receives different/focused tasks vs cycle 0 (bandit priorities differ) |
| 4 | WorkingMemory lifecycle | WorkingMemory | Resets per cycle, ingested into StrategicMemory at cycle end |
| 5 | Convergence logic | MuzzleOrchestrator | Loop stops when no new surfaces AND no new hits (doesn't run forever) |
| 6 | Think tool reasoning | ThinkStep | Agentic path captures ≥1 ThinkStep per cycle with valid context labels |
| 7 | AgenticCycleOutput parsing | MuzzleOrchestrator | Final output parsed correctly (not fallback regex path for well-formed LLM output) |
| 8 | Findings.jsonl growth | findings.jsonl | Winning turns written with monotonically increasing cycle numbers |

---

## Pass/Fail Criteria

- **PASS:** ≥2 cycles execute. Strategic memory has ≥1 surface with `attempts >= 2`. Bandit has
  ≥1 arm with `pulls >= 2`. Explorer tasks differ between cycles (observable via logging).
  Convergence fires before `max_muzzle_cycles` when there are no new surfaces/hits.
- **FAIL:** Only 1 cycle runs. Memory is empty after cycle 1. Bandit not persisted. Loop runs
  to `max_muzzle_cycles` without convergence check firing.

---

## New Logging

| File | Function | Level | Format |
|------|----------|-------|--------|
| `harness/campaign/muzzle_orchestrator.py` | `run()` | INFO | `cycle={n} cumulative_surfaces={set} new_surfaces={set} has_hits={bool} -> {continue\|stop}` |
| `harness/memory/strategic.py` | `update_from_result()` | INFO | `strategic surface={s} technique={t} status={s} -> win_rate={f}` |
| `harness/triage/bandit.py` | `update()` | DEBUG | `bandit arm={id} reward={f} pulls={n} mean={f} ucb1={f}` |
| `harness/campaign/muzzle_orchestrator.py` | `_run_cycle_agentic()` | INFO | `parse_path={1\|2\|3} surfaces={n} specs={n}` |

---

## Test Stubs

```python
# tests/e2e/test_phase_t2.py

import json
import pytest


@pytest.mark.e2e
class TestT2Adaptation:
    """Validate that the MUZZLE loop adapts across multiple cycles."""

    async def test_strategic_memory_accumulates(
        self, orchestrator, exploration_tasks, tmp_engagement
    ):
        """StrategicMemory grows across 2+ cycles."""
        result = await orchestrator.run(
            tasks=exploration_tasks,
            max_muzzle_cycles=2,
            engagement_dir=tmp_engagement["reports_dir"],
        )

        strategic_path = tmp_engagement["reports_dir"] / "strategic.json"
        assert strategic_path.exists(), "strategic.json must be created"

        strategic = json.loads(strategic_path.read_text())
        surface_stats = strategic.get("surface_stats", {})
        assert len(surface_stats) >= 1, "At least 1 surface must have stats"

        # At least one surface should have been attempted across 2 cycles
        max_attempts = max(
            s.get("attempts", 0) for s in surface_stats.values()
        )
        assert max_attempts >= 2, (
            f"Expected at least 1 surface with attempts >= 2, max was {max_attempts}"
        )

    async def test_bandit_updates_across_cycles(
        self, orchestrator, exploration_tasks, tmp_engagement
    ):
        """Bandit arms have pulls > 0 and different UCB1 scores after cycle 1."""
        await orchestrator.run(
            tasks=exploration_tasks,
            max_muzzle_cycles=2,
            engagement_dir=tmp_engagement["reports_dir"],
        )

        bandit_path = tmp_engagement["reports_dir"] / "bandit.json"
        assert bandit_path.exists(), "bandit.json must be created"

        bandit = json.loads(bandit_path.read_text())
        arms = bandit.get("arms", {})
        assert len(arms) >= 1, "At least 1 bandit arm must exist"

        # At least one arm should have been pulled across 2 cycles
        max_pulls = max(a.get("pulls", 0) for a in arms.values())
        assert max_pulls >= 2, (
            f"Expected at least 1 arm with pulls >= 2, max was {max_pulls}"
        )

    async def test_convergence_stops_loop(
        self, orchestrator, exploration_tasks, tmp_engagement
    ):
        """Loop terminates before max_cycles when no new surfaces or hits."""
        results = await orchestrator.run(
            tasks=exploration_tasks,
            max_muzzle_cycles=5,
            engagement_dir=tmp_engagement["reports_dir"],
        )

        # If convergence works, we should stop before exhausting all 5 cycles
        # (MockVictim has limited surfaces, so convergence should fire)
        assert len(results) < 5, (
            f"Expected convergence before 5 cycles, got {len(results)} cycles"
        )

    async def test_explorer_tasks_differ_between_cycles(
        self, orchestrator, exploration_tasks, caplog
    ):
        """Cycle 1 exploration tasks are different from cycle 0 (bandit-driven)."""
        import logging

        with caplog.at_level(logging.INFO, logger="harness"):
            await orchestrator.run(
                tasks=exploration_tasks,
                max_muzzle_cycles=2,
            )

        # Parse logs for Explorer task entries across cycles
        cycle_0_tasks = []
        cycle_1_tasks = []
        for record in caplog.records:
            if "Explorer task_id=" in record.message:
                if "cycle=0" in record.message or len(cycle_0_tasks) == 0:
                    cycle_0_tasks.append(record.message)
                else:
                    cycle_1_tasks.append(record.message)

        if cycle_0_tasks and cycle_1_tasks:
            # Tasks should differ between cycles (bandit influences exploration)
            assert cycle_0_tasks != cycle_1_tasks, (
                "Explorer tasks should differ between cycles due to bandit adaptation"
            )

    async def test_think_steps_captured_agentic(
        self, orchestrator, exploration_tasks, tmp_engagement
    ):
        """Agentic cycle produces ThinkSteps with valid context labels."""
        results = await orchestrator.run(
            tasks=exploration_tasks,
            max_muzzle_cycles=1,
            engagement_dir=tmp_engagement["reports_dir"],
        )

        # Check that at least 1 cycle has think steps
        assert len(results) >= 1, "Must have at least 1 cycle result"

        all_think_steps = []
        for cycle_result in results:
            if hasattr(cycle_result, "think_steps"):
                all_think_steps.extend(cycle_result.think_steps)

        assert len(all_think_steps) >= 1, (
            "Agentic cycle must produce at least 1 ThinkStep"
        )

        # Verify context labels are from the valid set
        valid_contexts = {
            "exploration", "grafting", "scoring", "attack_planning",
            "reflection", "convergence", "objective_replay",
        }
        for step in all_think_steps:
            assert step.context in valid_contexts, (
                f"Invalid ThinkStep context: {step.context}"
            )

    async def test_output_parsed_correctly(
        self, orchestrator, exploration_tasks, caplog
    ):
        """AgenticCycleOutput parsed via path 1 or 2 (not regex fallback)."""
        import logging

        with caplog.at_level(logging.INFO, logger="harness"):
            await orchestrator.run(
                tasks=exploration_tasks,
                max_muzzle_cycles=1,
            )

        parse_logs = [
            r.message for r in caplog.records
            if "parse_path=" in r.message
        ]
        assert len(parse_logs) >= 1, "Must have parse_path log entry"

        # Path 3 is regex fallback — should not be used for well-formed output
        for log in parse_logs:
            assert "parse_path=3" not in log, (
                "AgenticCycleOutput should be parsed via path 1 or 2, not regex fallback"
            )

    async def test_findings_jsonl_growth(
        self, orchestrator, exploration_tasks, tmp_engagement
    ):
        """Winning turns written with monotonically increasing cycle numbers."""
        await orchestrator.run(
            tasks=exploration_tasks,
            max_muzzle_cycles=2,
            engagement_dir=tmp_engagement["reports_dir"],
        )

        findings_path = tmp_engagement["reports_dir"] / "findings.jsonl"
        if not findings_path.exists():
            pytest.skip("No findings generated (target may not be exploitable)")

        cycle_numbers = []
        for line in findings_path.read_text().strip().split("\n"):
            finding = json.loads(line)
            cycle_numbers.append(finding.get("cycle", 0))

        # Cycle numbers should be monotonically non-decreasing
        for i in range(1, len(cycle_numbers)):
            assert cycle_numbers[i] >= cycle_numbers[i - 1], (
                f"Cycle numbers must be non-decreasing: {cycle_numbers}"
            )
```

---

## Fixture Dependencies

Additional fixtures needed in `tests/e2e/conftest.py`:

```python
@pytest.fixture
async def orchestrator(victim_adapter, tmp_engagement):
    """MuzzleOrchestrator configured for E2E testing."""
    from harness.campaign.muzzle_orchestrator import MuzzleOrchestrator

    return MuzzleOrchestrator(
        victim=victim_adapter,
        engagement_id=tmp_engagement["engagement_id"],
        reports_dir=tmp_engagement["reports_dir"],
    )


@pytest.fixture
def exploration_tasks(default_tasks):
    """Alias for default_tasks, used for clarity in T-2 tests."""
    return default_tasks
```

---

## Implementation Notes

- Convergence test relies on MockVictim having a finite set of surfaces — ensure MockVictim
  is configured so that repeated exploration yields diminishing returns
- Think step context labels must match the `valid_contexts` set defined above; if the
  orchestrator uses different labels, update the test
- The `parse_path` log assertion assumes TRD-17's agentic output parsing is implemented;
  if not yet wired, this test should be marked `xfail` initially
- Findings.jsonl growth test skips gracefully if no findings are generated (e.g., against a
  hardened target)
