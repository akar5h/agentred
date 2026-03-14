"""Engagement report generator (Markdown + HTML) for MUZZLE findings."""
from __future__ import annotations

import html as _html
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from harness.reporting.finding_card import FindingCard


_SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
_SEVERITY_BADGE = {
    "critical": "CRITICAL",
    "high": "HIGH",
    "medium": "MEDIUM",
    "low": "LOW",
    "info": "INFO",
}


class EngagementReportGenerator:
    """Generates Markdown and HTML engagement reports from FindingCards."""

    def __init__(
        self,
        engagement_id: str,
        target_name: str = "",
        run_config_summary: dict[str, Any] | None = None,
    ):
        self.engagement_id = engagement_id
        self.target_name = target_name or "unknown"
        self.run_config_summary = run_config_summary or {}

    def _build_markdown(
        self,
        finding_cards: list[FindingCard],
        cycle_results: list[dict[str, Any]] | None = None,
    ) -> str:
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        cycle_results = cycle_results or []

        severity_counts = Counter(c.severity for c in finding_cards)
        total_findings = len(finding_cards)

        # Sort cards by severity
        sorted_cards = sorted(
            finding_cards,
            key=lambda c: (_SEVERITY_ORDER.get(c.severity, 9), c.scenario_id),
        )

        # Attack success rate from cycle_results
        total_specs = sum(cr.get("specs_executed", 0) for cr in cycle_results) or 0
        total_hits = sum(len(cr.get("hits", [])) for cr in cycle_results) or total_findings
        success_rate = f"{(total_hits / total_specs * 100):.1f}%" if total_specs else "N/A"

        lines = [
            f"# MUZZLE Engagement Report",
            "",
            f"**Engagement ID:** {self.engagement_id}",
            f"**Target:** {self.target_name}",
            f"**Date:** {now}",
            "",
            "## Executive Summary",
            "",
            f"- **Total findings:** {total_findings}",
            f"- **Critical:** {severity_counts.get('critical', 0)}",
            f"- **High:** {severity_counts.get('high', 0)}",
            f"- **Medium:** {severity_counts.get('medium', 0)}",
            f"- **Low:** {severity_counts.get('low', 0)}",
            f"- **Info:** {severity_counts.get('info', 0)}",
            f"- **Attack success rate:** {success_rate}",
            "",
        ]

        # Metrics table
        if cycle_results:
            lines.extend([
                "## Metrics",
                "",
                "| Metric | Value |",
                "|--------|-------|",
                f"| Cycles run | {len(cycle_results)} |",
                f"| Total specs executed | {total_specs} |",
                f"| Total findings | {total_findings} |",
                f"| Surfaces covered | {len(set(c.attack_surface for c in finding_cards if c.attack_surface))} |",
                "",
            ])

        # Finding cards section
        lines.extend(["## Findings", ""])

        for card in sorted_cards:
            badge = _SEVERITY_BADGE.get(card.severity, card.severity.upper())
            lines.append(f"### [{badge}] {card.title}")
            lines.append("")
            lines.append(f"- **Severity:** {badge}")
            lines.append(f"- **Scenario:** {card.scenario_id}")
            lines.append(f"- **Suite:** {card.suite_id}")
            if card.oracle_codes:
                lines.append(f"- **Oracle codes:** {', '.join(card.oracle_codes)}")
            if card.attack_surface:
                lines.append(f"- **Attack surface:** {card.attack_surface}")
            if card.technique_family:
                lines.append(f"- **Technique:** {card.technique_family}")
            if card.owasp:
                lines.append(f"- **OWASP:** {', '.join(card.owasp)}")
            if card.atlas:
                lines.append(f"- **ATLAS:** {', '.join(card.atlas)}")
            lines.append("")

            if card.reproduction_steps:
                lines.append("**Reproduction steps:**")
                lines.append("")
                for step in card.reproduction_steps:
                    lines.append(f"1. {step}")
                lines.append("")

            if card.final_response:
                lines.append("**Response excerpt:**")
                lines.append("")
                lines.append(f"> {card.final_response[:500]}")
                lines.append("")

            lines.append("---")
            lines.append("")

        # Reflection summary (failure reasons from cycle results)
        if cycle_results:
            lines.extend(["## Reflection Summary", ""])
            failure_reasons: list[str] = []
            for cr in cycle_results:
                for jr in cr.get("judge_results", []):
                    reason = jr.get("failure_reason") or ""
                    if reason:
                        failure_reasons.append(reason)
            if failure_reasons:
                reason_counts = Counter(failure_reasons)
                lines.append("| Failure Reason | Count |")
                lines.append("|----------------|-------|")
                for reason, count in reason_counts.most_common():
                    lines.append(f"| {reason} | {count} |")
                lines.append("")
            else:
                lines.append("No failure attributions recorded.")
                lines.append("")

        return "\n".join(lines)

    def generate_markdown(
        self,
        finding_cards: list[FindingCard],
        cycle_results: list[dict[str, Any]] | None = None,
        output_path: str | Path = "",
    ) -> Path:
        md = self._build_markdown(finding_cards, cycle_results)
        if not output_path:
            output_path = f"reports/{self.engagement_id}/engagement_report.md"
        p = Path(output_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(md, encoding="utf-8")
        return p

    def generate_html(
        self,
        finding_cards: list[FindingCard],
        cycle_results: list[dict[str, Any]] | None = None,
        output_path: str | Path = "",
    ) -> Path:
        md = self._build_markdown(finding_cards, cycle_results)
        html_body = _md_to_simple_html(md)
        html_doc = _wrap_html(html_body, title=f"MUZZLE Report — {self.engagement_id}")
        if not output_path:
            output_path = f"reports/{self.engagement_id}/engagement_report.html"
        p = Path(output_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(html_doc, encoding="utf-8")
        return p


# ---------------------------------------------------------------------------
# Minimal markdown → HTML converter (no external deps)
# ---------------------------------------------------------------------------


def _md_to_simple_html(md: str) -> str:
    """Convert a subset of markdown to HTML. Good enough for reports."""
    lines = md.split("\n")
    html_lines: list[str] = []
    in_list = False

    for line in lines:
        escaped = _html.escape(line)

        if escaped.startswith("### "):
            if in_list:
                html_lines.append("</ol>")
                in_list = False
            html_lines.append(f"<h3>{escaped[4:]}</h3>")
        elif escaped.startswith("## "):
            if in_list:
                html_lines.append("</ol>")
                in_list = False
            html_lines.append(f"<h2>{escaped[3:]}</h2>")
        elif escaped.startswith("# "):
            if in_list:
                html_lines.append("</ol>")
                in_list = False
            html_lines.append(f"<h1>{escaped[2:]}</h1>")
        elif escaped.startswith("- **"):
            html_lines.append(f"<p>{_bold(escaped[2:])}</p>")
        elif escaped.startswith("&gt; "):
            html_lines.append(f"<blockquote>{escaped[5:]}</blockquote>")
        elif escaped.startswith("---"):
            html_lines.append("<hr>")
        elif re.match(r"^\d+\.\s", escaped):
            if not in_list:
                html_lines.append("<ol>")
                in_list = True
            content = re.sub(r"^\d+\.\s", "", escaped)
            html_lines.append(f"<li>{content}</li>")
        elif escaped.startswith("|") and "---" not in escaped:
            # Table row
            cells = [c.strip() for c in escaped.split("|")[1:-1]]
            row = "".join(f"<td>{c}</td>" for c in cells)
            html_lines.append(f"<tr>{row}</tr>")
        elif escaped.strip() == "":
            if in_list:
                html_lines.append("</ol>")
                in_list = False
            html_lines.append("")
        else:
            html_lines.append(f"<p>{_bold(escaped)}</p>")

    if in_list:
        html_lines.append("</ol>")

    return "\n".join(html_lines)


def _bold(text: str) -> str:
    """Replace **text** with <strong>text</strong>."""
    return re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)


def _wrap_html(body: str, title: str = "MUZZLE Report") -> str:
    return f"""\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{_html.escape(title)}</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
         max-width: 900px; margin: 2rem auto; padding: 0 1rem; color: #1a1a1a; }}
  h1 {{ border-bottom: 2px solid #333; padding-bottom: 0.3rem; }}
  h2 {{ border-bottom: 1px solid #ccc; padding-bottom: 0.2rem; margin-top: 2rem; }}
  h3 {{ margin-top: 1.5rem; }}
  table {{ border-collapse: collapse; width: 100%; margin: 1rem 0; }}
  td, th {{ border: 1px solid #ddd; padding: 6px 10px; text-align: left; }}
  tr:nth-child(even) {{ background: #f9f9f9; }}
  blockquote {{ border-left: 3px solid #ccc; margin: 0.5rem 0; padding: 0.5rem 1rem;
                background: #f5f5f5; white-space: pre-wrap; }}
  hr {{ border: none; border-top: 1px solid #eee; margin: 1.5rem 0; }}
  code {{ background: #f0f0f0; padding: 2px 4px; border-radius: 3px; }}
</style>
</head>
<body>
{body}
</body>
</html>
"""
