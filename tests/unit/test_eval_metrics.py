"""Tests for harness.campaign.eval_metrics — EvalMetrics, compute_metrics, format_comparison_markdown."""
from __future__ import annotations

from types import SimpleNamespace

from harness.campaign.eval_metrics import (
    EvalMetrics,
    compute_metrics,
    format_comparison_markdown,
)


def _make_cycle(surfaces, grafted, judge_count=0, validation=None, think_steps=None):
    return SimpleNamespace(
        surfaces_found=surfaces,
        vessels_grafted=grafted,
        judge_results=[{}] * judge_count,
        validation=validation or {},
        think_steps=think_steps or [],
    )


class TestComputeMetrics:
    def test_empty(self):
        m = compute_metrics("scripted", [], [], 0)
        assert m.mode == "scripted"
        assert m.surface_coverage == 0.0
        assert m.total_specs == 0
        assert m.total_successes == 0
        assert m.surfaces_found == []
        assert m.think_step_count == 0
        assert m.validation_score == 0.0

    def test_basic(self):
        cycles = [
            _make_cycle(["direct_chat", "file_upload"], 3),
            _make_cycle(["doc_memory"], 2),
        ]
        judge_rows = [
            {"status": "Success", "turn_count": 2},
            {"status": "Blocked", "turn_count": 3},
            {"status": "Success", "turn_count": 1},
        ]
        m = compute_metrics("agentic", cycles, judge_rows, total_tokens=10_000)
        assert m.mode == "agentic"
        assert m.surface_coverage == 3 / 7
        assert m.total_specs == 5
        assert m.total_successes == 2
        assert m.total_turns == 6
        assert m.win_rate == 2 / 5
        assert abs(m.budget_efficiency - (2 / 10_000) * 1000) < 1e-6
        assert abs(m.turn_efficiency - 2 / 6) < 1e-6
        assert sorted(m.surfaces_found) == ["direct_chat", "doc_memory", "file_upload"]

    def test_think_steps(self):
        cycles = [
            _make_cycle(["s1"], 1, think_steps=[{"r": "a"}, {"r": "b"}]),
            _make_cycle(["s2"], 1, think_steps=[{"r": "c"}]),
        ]
        m = compute_metrics("agentic", cycles, [], 0)
        assert m.think_step_count == 3

    def test_validation_score(self):
        cycles = [
            _make_cycle(["s1"], 1, validation={"quality_score": 0.8}),
            _make_cycle(["s2"], 1, validation={"quality_score": 0.6}),
        ]
        m = compute_metrics("scripted", cycles, [], 0)
        assert abs(m.validation_score - 0.7) < 1e-6

    def test_validation_score_no_data(self):
        cycles = [
            _make_cycle(["s1"], 1, validation={}),
        ]
        m = compute_metrics("scripted", cycles, [], 0)
        assert m.validation_score == 0.0


class TestFormatComparisonMarkdown:
    def test_structure(self):
        s = EvalMetrics(mode="scripted", surface_coverage=0.3, win_rate=0.5)
        a = EvalMetrics(mode="agentic", surface_coverage=0.6, win_rate=0.7, think_step_count=5)
        md = format_comparison_markdown(s, a, "eval-test")
        assert "eval-test" in md
        assert "Metrics Comparison" in md
        assert "Raw Numbers" in md
        assert "Surfaces Found" in md
        assert "Scripted" in md
        assert "Agentic" in md
        assert "Delta" in md

    def test_deltas(self):
        s = EvalMetrics(mode="scripted", surface_coverage=0.3, think_step_count=0)
        a = EvalMetrics(mode="agentic", surface_coverage=0.6, think_step_count=4)
        md = format_comparison_markdown(s, a, "eval-delta")
        # Think steps delta should be +4
        assert "+4" in md
        # Surface coverage delta should be positive
        assert "+30.0%" in md


class TestEvalMetricsToDict:
    def test_round_trip(self):
        m = EvalMetrics(
            mode="agentic",
            surface_coverage=0.42857,
            budget_efficiency=0.12345,
            turn_efficiency=0.33333,
            win_rate=0.5,
            exploration_ratio=0.6,
            total_tokens=5000,
            total_turns=10,
            total_specs=4,
            total_successes=2,
            surfaces_found=["a", "b", "c"],
            think_step_count=3,
            validation_score=0.85,
        )
        d = m.to_dict()
        assert d["mode"] == "agentic"
        assert d["surface_coverage"] == 0.429
        assert d["budget_efficiency"] == 0.1235
        assert d["turn_efficiency"] == 0.3333
        assert d["total_tokens"] == 5000
        assert d["surfaces_found"] == ["a", "b", "c"]
        assert d["think_step_count"] == 3
        assert d["validation_score"] == 0.85
