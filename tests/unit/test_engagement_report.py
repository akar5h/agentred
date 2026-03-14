"""Tests for EngagementReportGenerator."""
from __future__ import annotations

from pathlib import Path

import pytest

from harness.reporting.engagement_report import EngagementReportGenerator
from harness.reporting.finding_card import FindingCard


def _make_card(**overrides) -> FindingCard:
    defaults = dict(
        card_id="c1",
        scenario_id="sc1",
        suite_id="su1",
        run_id="r1",
        severity="high",
        title="[direct_chat] prompt_leak",
        oracle_codes=["prompt_leak"],
        attack_surface="direct_chat",
        technique_family="prompt_injection",
        reproduction_steps=["[turn 1] Hello", "[turn 2] Leak prompt"],
        final_response="Here is my system prompt...",
        canary_token="CANARY_abc",
        owasp=["LLM01"],
        atlas=[],
    )
    defaults.update(overrides)
    return FindingCard(**defaults)


class TestEngagementReportMarkdown:
    def test_generates_markdown_file(self, tmp_path: Path):
        gen = EngagementReportGenerator(
            engagement_id="test-eng-1",
            target_name="test-victim",
        )
        cards = [
            _make_card(severity="critical", title="[direct_chat] canary_exfiltrated"),
            _make_card(card_id="c2", severity="high", scenario_id="sc2"),
            _make_card(card_id="c3", severity="low", scenario_id="sc3"),
        ]
        out = gen.generate_markdown(cards, output_path=tmp_path / "report.md")
        assert out.exists()
        content = out.read_text()
        assert "# MUZZLE Engagement Report" in content
        assert "test-eng-1" in content
        assert "test-victim" in content
        assert "CRITICAL" in content
        assert "HIGH" in content
        assert "LOW" in content

    def test_executive_summary_counts(self, tmp_path: Path):
        gen = EngagementReportGenerator(engagement_id="e1")
        cards = [
            _make_card(severity="critical"),
            _make_card(card_id="c2", severity="critical"),
            _make_card(card_id="c3", severity="medium"),
        ]
        out = gen.generate_markdown(cards, output_path=tmp_path / "r.md")
        content = out.read_text()
        assert "**Critical:** 2" in content
        assert "**Medium:** 1" in content

    def test_empty_cards(self, tmp_path: Path):
        gen = EngagementReportGenerator(engagement_id="e2")
        out = gen.generate_markdown([], output_path=tmp_path / "empty.md")
        content = out.read_text()
        assert "**Total findings:** 0" in content


class TestEngagementReportHTML:
    def test_generates_html_file(self, tmp_path: Path):
        gen = EngagementReportGenerator(
            engagement_id="html-eng",
            target_name="html-victim",
        )
        cards = [_make_card()]
        out = gen.generate_html(cards, output_path=tmp_path / "report.html")
        assert out.exists()
        content = out.read_text()
        assert "<!DOCTYPE html>" in content
        assert "html-eng" in content
        assert "<h1>" in content

    def test_html_contains_findings(self, tmp_path: Path):
        gen = EngagementReportGenerator(engagement_id="e3")
        cards = [
            _make_card(severity="critical", title="[chat] canary_exfiltrated"),
        ]
        out = gen.generate_html(cards, output_path=tmp_path / "r.html")
        content = out.read_text()
        assert "CRITICAL" in content
        assert "canary_exfiltrated" in content


class TestEngagementReportWithCycleResults:
    def test_metrics_table_from_cycle_results(self, tmp_path: Path):
        gen = EngagementReportGenerator(engagement_id="e4")
        cards = [_make_card()]
        cycle_results = [
            {"specs_executed": 5, "hits": [{"s": 1}], "judge_results": []},
            {"specs_executed": 3, "hits": [], "judge_results": [
                {"failure_reason": "NOT_SURFACED"},
                {"failure_reason": "NOT_SURFACED"},
            ]},
        ]
        out = gen.generate_markdown(cards, cycle_results, output_path=tmp_path / "r.md")
        content = out.read_text()
        assert "Cycles run | 2" in content
        assert "Total specs executed | 8" in content
        assert "NOT_SURFACED" in content
