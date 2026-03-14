# TRD-22: Phase T-3 — Full Engagement

**Prerequisite:** TRD-21 (Phase T-2) passing — multi-cycle adaptation validated.

**Goal:** Prove that a complete `run_desert.py`-style execution produces all expected artifacts,
the engagement report is accurate, and the system is ready for real red-team use.

---

## What to Validate

| # | Check | Pass Condition |
|---|-------|----------------|
| 1 | All output artifacts generated | `runs.jsonl`, `runs.csv`, `report.md`, `telemetry.jsonl`, `run_meta.json` all exist and are non-empty |
| 2 | EngagementReport accuracy | Markdown/HTML report finding counts match JSONL data. Severity distribution correct |
| 3 | run_meta.json completeness | Contains config, catalog info, muzzle cycle details, eval_metrics |
| 4 | Eval metrics meaningful | `win_rate >= 0.0`, `surface_coverage >= 0.0`, budget_efficiency computed |
| 5 | FindingCards match JSONL | Number of cards == number of SUCCESS/INJECTION/PARTIAL results |
| 6 | Engagement report generated | `engagement_report.md` and `engagement_report.html` exist in reports dir |
| 7 | No crashes | Both `--scripted-only` and default (agentic) modes complete without Python tracebacks |
| 8 | Wall-clock timing | Total run completes within reasonable bounds (< 10 min for desert catalog) |

---

## Pass/Fail Criteria

- **PASS:** Exit code 0. All 5 base output files + 2 engagement report files exist and are
  non-empty. Eval metrics parse correctly. No tracebacks in stderr.
- **FAIL:** Exit non-zero, missing files, or unhandled exceptions.

---

## New Code Needed

| File | What |
|------|------|
| `scripts/run_desert.py` | Add wall-clock timing per layer |
| `scripts/run_desert.py` | Fix `total_tokens=0` gap — plumb `budget_tracker.campaign_usage` into `run_meta.json` |
| `scripts/run_desert.py` | Generate `EngagementReport` at end of run |
| `scripts/run_desert.py` | Add `--generate-report` flag to emit `engagement_report.{md,html}` |

---

## Test Stubs

```python
# tests/e2e/test_phase_t3.py

import json
import time
import pytest
from pathlib import Path


@pytest.mark.e2e
class TestT3FullEngagement:
    """Validate complete run_desert.py execution and artifact generation."""

    async def test_desert_run_completes(self, desert_config, tmp_reports_dir):
        """Full run_desert.py completes without crashes."""
        from scripts.run_desert import run_engagement

        try:
            await run_engagement(
                config=desert_config,
                reports_dir=tmp_reports_dir,
            )
        except Exception as e:
            pytest.fail(f"run_desert.py raised exception: {e}")

    async def test_all_artifacts_generated(self, completed_run_dir):
        """All 5 output files exist and are non-empty."""
        expected_files = [
            "runs.jsonl",
            "runs.csv",
            "report.md",
            "telemetry.jsonl",
            "run_meta.json",
        ]
        for filename in expected_files:
            path = completed_run_dir / filename
            assert path.exists(), f"Missing output file: {filename}"
            assert path.stat().st_size > 0, f"Output file is empty: {filename}"

    async def test_engagement_report_exists(self, completed_run_dir):
        """Engagement report files (md + html) exist and are non-empty."""
        for ext in ("md", "html"):
            path = completed_run_dir / f"engagement_report.{ext}"
            assert path.exists(), f"Missing engagement_report.{ext}"
            assert path.stat().st_size > 0, f"engagement_report.{ext} is empty"

    async def test_engagement_report_matches_jsonl(self, completed_run_dir):
        """FindingCard count in report matches SUCCESS/INJECTION count in JSONL."""
        # Count results from JSONL
        jsonl_path = completed_run_dir / "runs.jsonl"
        finding_statuses = {"SUCCESS", "INJECTION", "PARTIAL"}
        jsonl_finding_count = 0
        for line in jsonl_path.read_text().strip().split("\n"):
            row = json.loads(line)
            if row.get("status") in finding_statuses:
                jsonl_finding_count += 1

        # Parse report for finding count
        report_path = completed_run_dir / "engagement_report.md"
        report_text = report_path.read_text()

        # Report should contain a summary line with the finding count
        # (exact format depends on EngagementReport implementation)
        assert str(jsonl_finding_count) in report_text or jsonl_finding_count == 0, (
            f"Report finding count should match JSONL count ({jsonl_finding_count})"
        )

    async def test_eval_metrics_valid(self, completed_run_dir):
        """run_meta.json contains valid eval metrics."""
        meta_path = completed_run_dir / "run_meta.json"
        meta = json.loads(meta_path.read_text())

        eval_metrics = meta.get("eval_metrics", {})
        assert "win_rate" in eval_metrics, "Missing win_rate in eval_metrics"
        assert "surface_coverage" in eval_metrics, "Missing surface_coverage"
        assert "budget_efficiency" in eval_metrics, "Missing budget_efficiency"

        assert isinstance(eval_metrics["win_rate"], (int, float))
        assert eval_metrics["win_rate"] >= 0.0
        assert isinstance(eval_metrics["surface_coverage"], (int, float))
        assert eval_metrics["surface_coverage"] >= 0.0
        assert isinstance(eval_metrics["budget_efficiency"], (int, float))

    async def test_run_meta_has_cycle_details(self, completed_run_dir):
        """run_meta.json contains muzzle cycle details with surfaces and validation."""
        meta_path = completed_run_dir / "run_meta.json"
        meta = json.loads(meta_path.read_text())

        muzzle = meta.get("muzzle", {})
        cycles = muzzle.get("cycles", [])
        assert len(cycles) >= 1, "run_meta must contain at least 1 cycle"

        for i, cycle in enumerate(cycles):
            assert "surfaces_found" in cycle, f"Cycle {i} missing surfaces_found"
            assert "vessels_grafted" in cycle, f"Cycle {i} missing vessels_grafted"

    async def test_finding_cards_match_jsonl(self, completed_run_dir):
        """Number of FindingCards matches SUCCESS/INJECTION/PARTIAL count in JSONL."""
        jsonl_path = completed_run_dir / "runs.jsonl"
        finding_statuses = {"SUCCESS", "INJECTION", "PARTIAL"}
        expected_count = 0
        for line in jsonl_path.read_text().strip().split("\n"):
            row = json.loads(line)
            if row.get("status") in finding_statuses:
                expected_count += 1

        meta_path = completed_run_dir / "run_meta.json"
        meta = json.loads(meta_path.read_text())
        actual_count = meta.get("finding_card_count", 0)

        assert actual_count == expected_count, (
            f"FindingCard count ({actual_count}) != JSONL finding count ({expected_count})"
        )

    async def test_no_tracebacks_in_output(self, desert_config, tmp_reports_dir, capsys):
        """No Python tracebacks appear in stdout/stderr."""
        from scripts.run_desert import run_engagement

        await run_engagement(
            config=desert_config,
            reports_dir=tmp_reports_dir,
        )

        captured = capsys.readouterr()
        assert "Traceback" not in captured.err, (
            f"Python traceback found in stderr:\n{captured.err[:500]}"
        )

    async def test_wall_clock_timing(self, desert_config, tmp_reports_dir):
        """Total run completes within 10 minutes for desert catalog."""
        from scripts.run_desert import run_engagement

        start = time.monotonic()
        await run_engagement(
            config=desert_config,
            reports_dir=tmp_reports_dir,
        )
        elapsed = time.monotonic() - start

        assert elapsed < 600, (
            f"Run took {elapsed:.1f}s, expected < 600s (10 min)"
        )
```

---

## Fixture Dependencies

Additional fixtures needed in `tests/e2e/conftest.py`:

```python
@pytest.fixture
def desert_config(victim_adapter, tmp_engagement):
    """Configuration dict matching run_desert.py expected format."""
    return {
        "victim_adapter": victim_adapter,
        "engagement_id": tmp_engagement["engagement_id"],
        "catalog": "desert",
        "max_muzzle_cycles": 2,
        "generate_report": True,
    }


@pytest.fixture
def tmp_reports_dir(tmp_path):
    """Temporary reports directory for full engagement output."""
    reports = tmp_path / "reports"
    reports.mkdir()
    return reports


@pytest.fixture
async def completed_run_dir(desert_config, tmp_reports_dir):
    """Run a full engagement and return the reports directory."""
    from scripts.run_desert import run_engagement

    await run_engagement(
        config=desert_config,
        reports_dir=tmp_reports_dir,
    )
    return tmp_reports_dir
```

---

## Implementation Notes

- The `run_engagement` function is assumed to be extracted from `run_desert.py`'s `main()` for
  testability. If it currently only works as a CLI script, the first implementation step is to
  refactor the core logic into an importable function.
- Wall-clock timing bound of 10 minutes assumes desert catalog with MockVictim. Against a real
  target with network latency, this bound may need adjustment.
- `total_tokens=0` bug must be fixed before T-3 eval metrics tests will pass — plumb
  `budget_tracker.campaign_usage` into `run_meta.json`.
- The `--generate-report` flag in `run_desert.py` should default to `True` for E2E tests.
