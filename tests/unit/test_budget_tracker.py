"""Tests for grafted.budget.tracker — BudgetTracker, TokenUsage, BudgetStatus."""
from __future__ import annotations

import pytest

from grafted.budget.tracker import BudgetStatus, BudgetTracker, TokenUsage


class TestTokenUsage:
    def test_defaults(self):
        u = TokenUsage()
        assert u.input_tokens == 0
        assert u.output_tokens == 0
        assert u.est_cost == 0.0
        assert u.total_tokens == 0

    def test_add(self):
        u = TokenUsage()
        u.add(100, 50, 0.01)
        assert u.input_tokens == 100
        assert u.output_tokens == 50
        assert u.total_tokens == 150
        assert u.est_cost == pytest.approx(0.01)

    def test_add_cumulative(self):
        u = TokenUsage()
        u.add(100, 50)
        u.add(200, 100, 0.05)
        assert u.total_tokens == 450
        assert u.est_cost == pytest.approx(0.05)


class TestBudgetTracker:
    def test_initial_state_ok(self):
        bt = BudgetTracker(explorer_ceiling=1000, attacker_ceiling=2000, campaign_budget=10000)
        assert bt.check("explorer") == BudgetStatus.OK
        assert bt.check("attacker") == BudgetStatus.OK
        assert not bt.is_campaign_exhausted()

    def test_record_and_check_ok(self):
        bt = BudgetTracker(explorer_ceiling=1000)
        bt.record("explorer", 100, 100)
        assert bt.check("explorer") == BudgetStatus.OK

    def test_check_warning_at_80_pct(self):
        bt = BudgetTracker(explorer_ceiling=1000)
        bt.record("explorer", 400, 400)  # 800/1000 = 80%
        assert bt.check("explorer") == BudgetStatus.WARNING_80_PCT

    def test_check_exhausted_at_ceiling(self):
        bt = BudgetTracker(explorer_ceiling=1000)
        bt.record("explorer", 500, 500)  # 1000/1000 = 100%
        assert bt.check("explorer") == BudgetStatus.EXHAUSTED

    def test_check_exhausted_over_ceiling(self):
        bt = BudgetTracker(explorer_ceiling=1000)
        bt.record("explorer", 600, 600)  # 1200/1000 > 100%
        assert bt.check("explorer") == BudgetStatus.EXHAUSTED

    def test_unknown_agent_returns_ok(self):
        bt = BudgetTracker()
        assert bt.check("unknown_agent") == BudgetStatus.OK

    def test_reset_cycle(self):
        bt = BudgetTracker(explorer_ceiling=1000, campaign_budget=50000)
        bt.record("explorer", 500, 500)
        assert bt.check("explorer") == BudgetStatus.EXHAUSTED
        bt.reset_cycle()
        assert bt.check("explorer") == BudgetStatus.OK
        # Campaign usage persists across resets
        assert bt.campaign_usage.total_tokens == 1000

    def test_campaign_exhaustion(self):
        bt = BudgetTracker(campaign_budget=500)
        bt.record("explorer", 200, 200)
        assert not bt.is_campaign_exhausted()
        bt.record("attacker", 100, 100)
        assert bt.is_campaign_exhausted()  # 600 >= 500

    def test_campaign_usage_accumulates_across_cycles(self):
        bt = BudgetTracker(explorer_ceiling=1000, campaign_budget=5000)
        bt.record("explorer", 200, 200)
        bt.reset_cycle()
        bt.record("explorer", 300, 300)
        assert bt.campaign_usage.total_tokens == 1000

    def test_cycle_usage_accessor(self):
        bt = BudgetTracker()
        bt.record("explorer", 100, 50)
        usage = bt.cycle_usage("explorer")
        assert usage.input_tokens == 100
        assert usage.output_tokens == 50

    def test_cycle_usage_missing_agent(self):
        bt = BudgetTracker()
        usage = bt.cycle_usage("nonexistent")
        assert usage.total_tokens == 0

    def test_to_telemetry_dict(self):
        bt = BudgetTracker(explorer_ceiling=10000, campaign_budget=50000)
        bt.record("explorer", 100, 200, 0.03)
        d = bt.to_telemetry_dict()
        assert "cycle_usage" in d
        assert d["cycle_usage"]["explorer"]["total_tokens"] == 300
        assert d["cycle_usage"]["explorer"]["est_cost"] == pytest.approx(0.03)
        assert d["campaign_total_tokens"] == 300
        assert d["campaign_exhausted"] is False

    def test_multiple_agents_tracked_independently(self):
        bt = BudgetTracker(explorer_ceiling=1000, attacker_ceiling=2000)
        bt.record("explorer", 400, 400)  # 80% of 1000
        bt.record("attacker", 400, 400)  # 40% of 2000
        assert bt.check("explorer") == BudgetStatus.WARNING_80_PCT
        assert bt.check("attacker") == BudgetStatus.OK
