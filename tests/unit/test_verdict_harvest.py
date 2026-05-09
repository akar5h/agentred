"""Tests for the AgentDojo verdict harvester. No agentdojo dep needed."""
from __future__ import annotations

import json
from pathlib import Path

from grafted.integrations.agentdojo.verdict_harvest import VerdictHarvester


def _write_log(
    logdir: Path,
    pipeline: str,
    suite: str,
    user_task_id: str,
    injection_task_id: str,
    attack_name: str,
    utility: bool,
    security: bool,
) -> None:
    log_path = logdir / pipeline / suite / user_task_id / attack_name / f"{injection_task_id}.json"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(json.dumps({
        "user_task_id": user_task_id,
        "injection_task_id": injection_task_id,
        "utility": utility,
        "security": security,
        "suite_name": suite,
        "pipeline_name": pipeline,
    }))


def test_harvester_yields_verdicts(tmp_path: Path) -> None:
    _write_log(tmp_path, "gpt-4o", "workspace", "user_task_0", "injection_task_0",
               "grafted", utility=True, security=False)
    _write_log(tmp_path, "gpt-4o", "workspace", "user_task_1", "injection_task_2",
               "grafted", utility=False, security=True)

    h = VerdictHarvester(tmp_path, "gpt-4o", "workspace", "grafted")
    verdicts = list(h.new_verdicts("eng-1"))
    assert len(verdicts) == 2
    by_user = {v.user_task_id: v for v in verdicts}
    assert by_user["user_task_0"].security is False
    assert by_user["user_task_1"].security is True
    assert by_user["user_task_0"].utility is True


def test_harvester_dedup_per_engagement(tmp_path: Path) -> None:
    _write_log(tmp_path, "gpt-4o", "workspace", "user_task_0", "injection_task_0",
               "grafted", utility=True, security=False)

    h = VerdictHarvester(tmp_path, "gpt-4o", "workspace", "grafted")
    first = list(h.new_verdicts("eng-1"))
    second = list(h.new_verdicts("eng-1"))
    assert len(first) == 1
    assert len(second) == 0


def test_harvester_per_engagement_isolation(tmp_path: Path) -> None:
    _write_log(tmp_path, "gpt-4o", "workspace", "user_task_0", "injection_task_0",
               "grafted", utility=True, security=False)

    h = VerdictHarvester(tmp_path, "gpt-4o", "workspace", "grafted")
    list(h.new_verdicts("eng-A"))  # consume for A
    fresh_for_b = list(h.new_verdicts("eng-B"))  # B hasn't seen them
    assert len(fresh_for_b) == 1


def test_harvester_ignores_other_attacks(tmp_path: Path) -> None:
    _write_log(tmp_path, "gpt-4o", "workspace", "user_task_0", "injection_task_0",
               "grafted", utility=True, security=False)
    _write_log(tmp_path, "gpt-4o", "workspace", "user_task_0", "injection_task_0",
               "important_instructions", utility=True, security=False)

    h = VerdictHarvester(tmp_path, "gpt-4o", "workspace", "grafted")
    verdicts = list(h.new_verdicts("eng-1"))
    assert len(verdicts) == 1


def test_harvester_skips_malformed(tmp_path: Path) -> None:
    log_dir = tmp_path / "gpt-4o" / "workspace" / "user_task_0" / "grafted"
    log_dir.mkdir(parents=True)
    (log_dir / "injection_task_0.json").write_text("not json")

    h = VerdictHarvester(tmp_path, "gpt-4o", "workspace", "grafted")
    assert list(h.new_verdicts("eng-1")) == []


def test_harvester_skips_missing_fields(tmp_path: Path) -> None:
    log_dir = tmp_path / "gpt-4o" / "workspace" / "user_task_0" / "grafted"
    log_dir.mkdir(parents=True)
    (log_dir / "injection_task_0.json").write_text(json.dumps({
        "user_task_id": "user_task_0",
        # missing injection_task_id, utility, security
    }))

    h = VerdictHarvester(tmp_path, "gpt-4o", "workspace", "grafted")
    assert list(h.new_verdicts("eng-1")) == []


def test_harvester_no_logdir_yet(tmp_path: Path) -> None:
    h = VerdictHarvester(tmp_path / "nonexistent", "gpt-4o", "workspace", "grafted")
    assert list(h.new_verdicts("eng-1")) == []
