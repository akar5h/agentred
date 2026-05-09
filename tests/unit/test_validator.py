"""Tests for grafted.campaign.validator — AgentValidator + ValidationReport."""
from __future__ import annotations

from grafted.campaign.validator import AgentValidator, ValidationReport, ValidationWarning


class TestAgentValidator:
    def _make_validator(self) -> AgentValidator:
        return AgentValidator()

    def test_perfect_cycle(self):
        v = self._make_validator()
        report = v.validate(
            cycle=1,
            surfaces_explored=["s1", "s2", "s3", "s4", "s5", "s6", "s7"],
            surface_stats={"s1": {"attempts": 3, "successes": 2}},
            total_attempts=10,
            total_successes=8,
            surfaces_discovered=5,
            specs_count=5,
            think_step_count=3,
        )
        assert report.quality_score >= 0.9
        # No warning or error-level warnings
        non_info = [w for w in report.warnings if w.severity != "info"]
        assert len(non_info) == 0

    def test_low_coverage_warning(self):
        v = self._make_validator()
        report = v.validate(
            cycle=1,
            surfaces_explored=["s1"],
            surface_stats={},
            total_attempts=0,
            total_successes=0,
            surfaces_discovered=1,
            specs_count=0,
            think_step_count=3,
        )
        coverage_warnings = [w for w in report.warnings if w.check == "surface_coverage"]
        assert len(coverage_warnings) == 1
        assert coverage_warnings[0].severity == "warning"

    def test_blocked_loop_error(self):
        v = self._make_validator()
        report = v.validate(
            cycle=0,
            surfaces_explored=["s1", "s2", "s3"],
            surface_stats={"s1": {"attempts": 5, "successes": 0}},
            total_attempts=5,
            total_successes=0,
            surfaces_discovered=3,
            specs_count=2,
            think_step_count=2,
        )
        blocked = [w for w in report.warnings if w.check == "blocked_loop"]
        assert len(blocked) == 1
        assert blocked[0].severity == "error"

    def test_budget_waste_warning(self):
        v = self._make_validator()
        report = v.validate(
            cycle=0,
            surfaces_explored=["s1", "s2", "s3"],
            surface_stats={},
            total_attempts=10,
            total_successes=0,
            surfaces_discovered=3,
            specs_count=2,
            think_step_count=2,
        )
        waste = [w for w in report.warnings if w.check == "budget_waste"]
        assert len(waste) == 1
        assert waste[0].severity == "warning"
        assert waste[0].metric_value == 1.0

    def test_low_exploration_ratio(self):
        v = self._make_validator()
        report = v.validate(
            cycle=0,
            surfaces_explored=["s1"],
            surface_stats={},
            total_attempts=0,
            total_successes=0,
            surfaces_discovered=0,
            specs_count=10,
            think_step_count=2,
        )
        expl = [w for w in report.warnings if w.check == "exploration_ratio"]
        assert len(expl) == 1
        assert expl[0].severity == "warning"
        assert expl[0].metric_value == 0.0

    def test_low_think_steps_info(self):
        v = self._make_validator()
        report = v.validate(
            cycle=0,
            surfaces_explored=["s1", "s2", "s3", "s4", "s5", "s6", "s7"],
            surface_stats={},
            total_attempts=0,
            total_successes=0,
            surfaces_discovered=7,
            specs_count=0,
            think_step_count=0,
        )
        think = [w for w in report.warnings if w.check == "think_steps"]
        assert len(think) == 1
        assert think[0].severity == "info"

    def test_quality_score_clamped(self):
        v = self._make_validator()
        # Many errors to push score below 0
        report = v.validate(
            cycle=1,
            surfaces_explored=[],
            surface_stats={
                f"s{i}": {"attempts": 3, "successes": 0} for i in range(10)
            },
            total_attempts=30,
            total_successes=0,
            surfaces_discovered=0,
            specs_count=10,
            think_step_count=0,
        )
        assert report.quality_score >= 0.0
        assert report.quality_score <= 1.0

        # Perfect scenario — score should not exceed 1.0
        report2 = v.validate(
            cycle=1,
            surfaces_explored=["s1", "s2", "s3", "s4", "s5", "s6", "s7"],
            surface_stats={"s1": {"attempts": 1, "successes": 1}},
            total_attempts=1,
            total_successes=1,
            surfaces_discovered=7,
            specs_count=0,
            think_step_count=5,
        )
        assert report2.quality_score <= 1.0
        assert report2.quality_score >= 0.0


class TestValidationReport:
    def test_report_to_dict(self):
        report = ValidationReport(
            cycle=2,
            quality_score=0.85,
            warnings=[
                ValidationWarning(
                    check="surface_coverage",
                    severity="warning",
                    message="Low coverage",
                    metric_value=0.14,
                ),
                ValidationWarning(
                    check="think_steps",
                    severity="info",
                    message="Few think steps",
                    metric_value=1.0,
                ),
            ],
            metrics={"coverage": 0.14, "waste_ratio": 0.0, "exploration_ratio": 0.5, "think_steps": 1},
        )
        d = report.to_dict()
        assert d["cycle"] == 2
        assert d["quality_score"] == 0.85
        assert len(d["warnings"]) == 2
        assert d["warnings"][0]["check"] == "surface_coverage"
        assert d["warnings"][0]["severity"] == "warning"
        assert d["warnings"][0]["message"] == "Low coverage"
        assert d["warnings"][0]["metric_value"] == 0.14
        assert d["warnings"][1]["check"] == "think_steps"
        assert d["metrics"]["coverage"] == 0.14
        assert d["metrics"]["think_steps"] == 1
