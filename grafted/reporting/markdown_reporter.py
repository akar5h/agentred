from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Union


def _status_value(value: Any) -> str:
    if hasattr(value, "value"):
        return str(value.value)
    return str(value or "")


def _normalize_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        item["status"] = _status_value(item.get("status", "Blocked"))
        if hasattr(item.get("failure_reason"), "value"):
            item["failure_reason"] = item["failure_reason"].value
        if hasattr(item.get("attack_surface"), "value"):
            item["attack_surface"] = item["attack_surface"].value
        hard_flags = item.get("hard_flags", {})
        if not isinstance(hard_flags, dict):
            hard_flags = {}
        item["hard_flags"] = hard_flags
        out.append(item)
    return out


def write_markdown_report(
    path: Union[str, Path],
    *,
    title: str,
    rows: list[dict[str, Any]],
    target_name: str = "",
    phase: int = 1,
) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)

    normalized = _normalize_rows(rows)
    total = len(normalized)
    counts = Counter(row.get("status", "Blocked") for row in normalized)

    lines = [
        f"# {title}",
        "",
        f"**Target:** {target_name or 'unknown'}",
        f"**Phase:** {phase}",
        f"**Date:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        f"**Total scenarios:** {total}",
        "",
        "## Summary",
        "",
        "| Status | Count | Rate |",
        "|--------|-------|------|",
    ]

    for status in ("Success", "Injection", "Partial", "Blocked", "InfraFail"):
        c = counts.get(status, 0)
        rate = f"{(c / total * 100):.1f}%" if total else "0.0%"
        lines.append(f"| {status} | {c} | {rate} |")

    lines.extend(["", "## Top Runs", ""])
    lines.append(
        "| Scenario | Suite | Status | FailureReason | SuggestedVariant | AttackSurface | Canary | Key Flags |"
    )
    lines.append("|----------|-------|--------|---------------|------------------|---------------|--------|----------|")

    def _sort_key(item: dict[str, Any]) -> tuple[int, int]:
        status_rank = {"Success": 0, "Injection": 1, "Partial": 2, "Blocked": 3, "InfraFail": 4}
        flags = item.get("hard_flags", {})
        active = sum(1 for _, v in flags.items() if v)
        return (status_rank.get(item.get("status", "Blocked"), 9), -active)

    for row in sorted(normalized, key=_sort_key)[:20]:
        flags = row.get("hard_flags", {})
        active_flags = [k for k, v in flags.items() if v]
        lines.append(
            "| {scenario_id} | {suite_id} | {status} | {failure_reason} | {suggested_variant} | {attack_surface} | {canary_token} | {active_flags} |".format(
                scenario_id=row.get("scenario_id", "?"),
                suite_id=row.get("suite_id", "?"),
                status=row.get("status", "?"),
                failure_reason=row.get("failure_reason") or "",
                suggested_variant=row.get("suggested_variant") or "",
                attack_surface=row.get("attack_surface") or "",
                canary_token=row.get("canary_token") or "",
                active_flags=", ".join(active_flags) or "none",
            )
        )

    reflection_rows = [row for row in normalized if row.get("failure_reason")]
    lines.extend(["", "## Reflection Summary", ""])
    lines.append("| FailureReason | Count | Most Common Scenario |")
    lines.append("|---------------|-------|----------------------|")

    if reflection_rows:
        by_reason: dict[str, list[str]] = {}
        for row in reflection_rows:
            reason = str(row.get("failure_reason", ""))
            by_reason.setdefault(reason, []).append(str(row.get("scenario_id", "")))

        for reason, scenarios in sorted(by_reason.items(), key=lambda x: len(x[1]), reverse=True):
            common_scenario = Counter(scenarios).most_common(1)[0][0] if scenarios else ""
            lines.append(f"| {reason} | {len(scenarios)} | {common_scenario} |")
    else:
        lines.append("| (none) | 0 | - |")

    p.write_text("\n".join(lines), encoding="utf-8")
