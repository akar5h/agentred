"""Tests for harness.budget.tool_counter — ToolCallCounter, ToolBudgetStatus."""
from __future__ import annotations

import pytest

from harness.budget.tool_counter import ToolBudgetStatus, ToolCallCounter


class TestToolCallCounter:
    def test_initial_state_ok(self):
        tc = ToolCallCounter(limits={"explorer": 10, "attacker": 5})
        assert tc.check("explorer") == ToolBudgetStatus.OK
        assert tc.check("attacker") == ToolBudgetStatus.OK

    def test_increment_returns_status(self):
        tc = ToolCallCounter(limits={"explorer": 10})
        status = tc.increment("explorer")
        assert status == ToolBudgetStatus.OK

    def test_warning_at_80_pct(self):
        tc = ToolCallCounter(limits={"explorer": 10})
        for _ in range(8):  # 80%
            tc.increment("explorer")
        assert tc.check("explorer") == ToolBudgetStatus.WARNING

    def test_exhausted_at_limit(self):
        tc = ToolCallCounter(limits={"explorer": 10})
        for _ in range(10):
            tc.increment("explorer")
        assert tc.check("explorer") == ToolBudgetStatus.EXHAUSTED

    def test_exhausted_over_limit(self):
        tc = ToolCallCounter(limits={"explorer": 5})
        for _ in range(5):
            tc.increment("explorer")
        status = tc.increment("explorer")  # 6th call
        assert status == ToolBudgetStatus.EXHAUSTED

    def test_remaining(self):
        tc = ToolCallCounter(limits={"explorer": 10})
        assert tc.remaining("explorer") == 10
        tc.increment("explorer")
        assert tc.remaining("explorer") == 9

    def test_remaining_at_zero(self):
        tc = ToolCallCounter(limits={"explorer": 2})
        tc.increment("explorer")
        tc.increment("explorer")
        assert tc.remaining("explorer") == 0
        tc.increment("explorer")
        assert tc.remaining("explorer") == 0  # Can't go negative

    def test_reset(self):
        tc = ToolCallCounter(limits={"explorer": 10})
        for _ in range(10):
            tc.increment("explorer")
        assert tc.check("explorer") == ToolBudgetStatus.EXHAUSTED
        tc.reset()
        assert tc.check("explorer") == ToolBudgetStatus.OK
        assert tc.remaining("explorer") == 10

    def test_unknown_agent_raises(self):
        tc = ToolCallCounter(limits={"explorer": 10})
        with pytest.raises(KeyError, match="Unknown agent"):
            tc.increment("unknown")

    def test_unknown_agent_check_raises(self):
        tc = ToolCallCounter(limits={"explorer": 10})
        with pytest.raises(KeyError, match="Unknown agent"):
            tc.check("unknown")

    def test_unknown_agent_remaining_raises(self):
        tc = ToolCallCounter(limits={"explorer": 10})
        with pytest.raises(KeyError, match="Unknown agent"):
            tc.remaining("unknown")

    def test_warning_message_exhausted(self):
        tc = ToolCallCounter(limits={"explorer": 1})
        tc.increment("explorer")
        msg = tc.warning_message("explorer")
        assert "BUDGET_EXHAUSTED" in msg

    def test_warning_message_warning(self):
        tc = ToolCallCounter(limits={"explorer": 10})
        for _ in range(9):
            tc.increment("explorer")
        msg = tc.warning_message("explorer")
        assert "1 tool calls remaining" in msg

    def test_warning_message_ok(self):
        tc = ToolCallCounter(limits={"explorer": 10})
        assert tc.warning_message("explorer") == ""


class TestToolCallCounterLenient:
    def test_lenient_increment_unknown_returns_ok(self):
        tc = ToolCallCounter(limits={"explorer": 10}, strict=False)
        status = tc.increment("unknown_agent")
        assert status == ToolBudgetStatus.OK

    def test_lenient_check_unknown_returns_ok(self):
        tc = ToolCallCounter(limits={"explorer": 10}, strict=False)
        assert tc.check("unknown_agent") == ToolBudgetStatus.OK

    def test_lenient_remaining_unknown_returns_zero(self):
        tc = ToolCallCounter(limits={"explorer": 10}, strict=False)
        assert tc.remaining("unknown_agent") == 0

    def test_lenient_known_agent_still_works(self):
        tc = ToolCallCounter(limits={"explorer": 5}, strict=False)
        for _ in range(5):
            tc.increment("explorer")
        assert tc.check("explorer") == ToolBudgetStatus.EXHAUSTED

    def test_strict_default_raises(self):
        tc = ToolCallCounter(limits={"explorer": 10})
        with pytest.raises(KeyError, match="Unknown agent"):
            tc.increment("unknown_agent")
