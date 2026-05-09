"""Tests for grafted.campaign.think_tool — ThinkLog + make_think_tool."""
from __future__ import annotations

from grafted.campaign.think_tool import ThinkLog, make_think_tool
from grafted.core.schemas import ThinkStep


# ---------------------------------------------------------------------------
# ThinkLog
# ---------------------------------------------------------------------------


class TestThinkLog:
    def test_empty(self):
        log = ThinkLog(cycle=0)
        assert log.steps == []
        assert log.to_telemetry_dicts() == []
        assert "0 think steps" in log.summary()

    def test_add(self):
        log = ThinkLog(cycle=1)
        step = ThinkStep(reasoning="checking surfaces", context="pre_exploration", cycle=1)
        log.add(step)
        assert len(log.steps) == 1
        assert log.steps[0].reasoning == "checking surfaces"

    def test_summary_format(self):
        log = ThinkLog(cycle=2)
        log.add(ThinkStep(reasoning="reason A", context="post_grafter", decision="graft", cycle=2))
        log.add(ThinkStep(reasoning="reason B", cycle=2))
        s = log.summary()
        assert "Cycle 2: 2 think step(s)" in s
        assert "reason A" in s
        assert "[post_grafter]" in s
        assert "-> graft" in s

    def test_telemetry_dicts(self):
        log = ThinkLog(cycle=0)
        log.add(ThinkStep(reasoning="r1", cycle=0))
        log.add(ThinkStep(reasoning="r2", context="hypothesis", cycle=0))
        dicts = log.to_telemetry_dicts()
        assert len(dicts) == 2
        assert dicts[0]["reasoning"] == "r1"
        assert dicts[1]["context"] == "hypothesis"


# ---------------------------------------------------------------------------
# make_think_tool
# ---------------------------------------------------------------------------


class TestMakeThinkTool:
    def test_returns_string(self):
        log = ThinkLog(cycle=0)
        think = make_think_tool(log, cycle=0, use_stream_writer=False)
        result = think.invoke({"reasoning": "test reasoning"})
        assert isinstance(result, str)
        assert "Recorded" in result

    def test_accumulates_steps(self):
        log = ThinkLog(cycle=3)
        think = make_think_tool(log, cycle=3, use_stream_writer=False)
        think.invoke({"reasoning": "step one", "context": "pre_exploration"})
        think.invoke({"reasoning": "step two", "context": "attack_planning", "decision": "attack"})
        assert len(log.steps) == 2
        assert log.steps[0].context == "pre_exploration"
        assert log.steps[1].decision == "attack"

    def test_sets_timestamp(self):
        log = ThinkLog(cycle=0)
        think = make_think_tool(log, cycle=0, use_stream_writer=False)
        think.invoke({"reasoning": "ts check"})
        assert log.steps[0].timestamp_iso != ""

    def test_sets_cycle(self):
        log = ThinkLog(cycle=5)
        think = make_think_tool(log, cycle=5, use_stream_writer=False)
        think.invoke({"reasoning": "cycle check"})
        assert log.steps[0].cycle == 5
