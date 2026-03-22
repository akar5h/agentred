"""Convert hr_ai_redteam phase2 catalogs to GART format.

Copies fixtures, maps oracle codes, sets attack_surface explicitly.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

HR_ROOT = Path.home() / "Documents" / "hr_ai_redteam"
GART_ROOT = Path(__file__).resolve().parents[1]
GART_FIXTURE_DIR = GART_ROOT / "harness" / "attack" / "fixtures" / "hr_ai"
GART_LIBRARY_DIR = GART_ROOT / "harness" / "attack" / "library" / "hr_ai"

# Phase2 oracle codes → GART OracleCode enum values
ORACLE_MAP: dict[str, str] = {
    "SYSTEM_PROMPT_LEAKED": "prompt_leak",
    "INSTRUCTION_ACKNOWLEDGED": "behavioral_leak",
    "SCHEMA_DISCLOSED": "schema_leak",
    "CANARY_ECHOED": "canary_exfiltrated",
    "CANARY_EXFILTRATED": "canary_exfiltrated",
    "SCORE_INFLATED": "policy_override",
    "MEMORY_POISONED_WRITE": "memory_write_poisoning",
    "MEMORY_POISONED_ACTIVE": "delayed_activation",
    "TOOL_HIJACKED": "tool_hijack_write",
    "EMAIL_INJECTED": "api_surface_exfil",
    "SEARCH_EXFIL_QUERY": "api_surface_exfil",
    "SCRAPE_EXFIL": "api_surface_exfil",
    "SQL_CROSS_TENANT": "out_of_scope_read",
    "TENANT_PIVOT": "cross_boundary_exfil",
    "RUBRIC_DISCLOSED": "high_value_exfil",
    "RUBRIC_OVERRIDDEN": "policy_override",
    "SHORTLIST_FORCED": "policy_override",
    "CROSS_AGENT_POISONED": "behavioral_leak",
    "DEDUP_BYPASSED": "policy_override",
}

# Catalog → explicit attack_surface (GART enum value)
SURFACE_MAP: dict[str, str] = {
    "indirect-injection": "indirect_upload",
    "direct-injection": "direct_chat",
    "tool-injection": "tool_poisoning",
    "data-exfiltration": "data_extraction",
    "tenant-boundary": "direct_chat",
    "memory-poisoning": "memory_poisoning",
    "score-manipulation": "tool_poisoning",
    "search-exfil": "external_api_exploitation",
    "multi-agent-split": "subagent_injection",
    "adaptive-multi-turn": "direct_chat",
}


def copy_fixtures() -> dict[str, str]:
    """Copy all hr_ai_redteam fixtures → GART fixture dir. Returns old→new path map."""
    path_map: dict[str, str] = {}
    src_fixture_dir = HR_ROOT / "fixtures"
    if not src_fixture_dir.exists():
        print(f"  WARN: {src_fixture_dir} not found, skipping fixture copy")
        return path_map

    GART_FIXTURE_DIR.mkdir(parents=True, exist_ok=True)

    for src in src_fixture_dir.rglob("*"):
        if src.is_dir():
            continue
        rel = src.relative_to(src_fixture_dir)
        dst = GART_FIXTURE_DIR / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        # Store mapping: original relative path → GART-relative path
        old_key = f"fixtures/{rel}"
        new_val = f"harness/attack/fixtures/hr_ai/{rel}"
        path_map[old_key] = new_val

    print(f"  Copied {len(path_map)} fixtures to {GART_FIXTURE_DIR}")
    return path_map


def convert_catalog(catalog_dir: str, fixture_map: dict[str, str]) -> dict | None:
    """Convert a single hr_ai_redteam phase2 catalog to GART format."""
    phase2_dir = HR_ROOT / "attack-library" / catalog_dir / "phase2"
    if not phase2_dir.exists():
        print(f"  SKIP: {phase2_dir} not found")
        return None

    jsons = list(phase2_dir.glob("*.json"))
    if not jsons:
        print(f"  SKIP: no JSON in {phase2_dir}")
        return None

    src_path = jsons[0]
    raw = json.loads(src_path.read_text(encoding="utf-8"))
    surface = SURFACE_MAP.get(catalog_dir, "direct_chat")

    gart_catalog: dict = {
        "suite_id": raw.get("suite_id", catalog_dir),
        "version": raw.get("version", "1.0.0"),
        "attack_surface": surface,
        "description": raw.get("description", f"Converted from hr_ai_redteam/{catalog_dir}"),
        "attacks": [],
    }

    for attack in raw.get("attacks", []):
        # Map oracle codes
        mapped_codes = []
        for code in attack.get("oracle_codes", []):
            mapped = ORACLE_MAP.get(code, code.lower())
            if mapped not in mapped_codes:
                mapped_codes.append(mapped)

        # Convert uploads → update fixture paths
        uploads = []
        for upload in attack.get("uploads", []):
            old_path = upload.get("fixture", "")
            new_path = fixture_map.get(old_path, old_path)
            uploads.append({
                "fixture": new_path,
                "format": upload.get("format", "txt"),
                "render": upload.get("render", True),
            })

        # Determine chain_mode from turn count
        turns = attack.get("turns", [])
        chain_mode = len(turns) >= 4

        gart_attack: dict = {
            "id": attack.get("id", ""),
            "category": attack.get("category", ""),
            "severity": attack.get("severity", ""),
            "owasp": attack.get("owasp", []),
            "atlas": attack.get("atlas", []),
            "technique_family": attack.get("technique_family", ""),
            "objective": attack.get("objective", attack.get("attack_goal", "")),
            "success_criteria": attack.get("success_criteria", ""),
            "turns": turns,
            "oracle_codes": mapped_codes,
            "expected": attack.get("expected", {}),
            "adaptive": True,
            "chain_mode": chain_mode,
            "max_chain_turns": max(len(turns), 8),
        }

        if uploads:
            gart_attack["uploads"] = uploads

        gart_catalog["attacks"].append(gart_attack)

    return gart_catalog


def main() -> None:
    print("Converting hr_ai_redteam phase2 catalogs → GART format\n")

    print("Step 1: Copy fixtures")
    fixture_map = copy_fixtures()

    print("\nStep 2: Convert catalogs")
    GART_LIBRARY_DIR.mkdir(parents=True, exist_ok=True)

    catalogs = [
        "indirect-injection",
        "direct-injection",
        "tool-injection",
        "data-exfiltration",
        "tenant-boundary",
        "memory-poisoning",
        "score-manipulation",
        "search-exfil",
        "multi-agent-split",
        "adaptive-multi-turn",
    ]

    total_attacks = 0
    for catalog_dir in catalogs:
        gart = convert_catalog(catalog_dir, fixture_map)
        if gart is None:
            continue

        out_name = catalog_dir.replace("-", "_") + "_v1.json"
        out_path = GART_LIBRARY_DIR / out_name
        out_path.write_text(
            json.dumps(gart, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        n = len(gart["attacks"])
        total_attacks += n
        print(f"  {catalog_dir}: {n} attacks → {out_path.name}")

    print(f"\nDone: {total_attacks} attacks across {len(catalogs)} catalogs")
    print(f"Output: {GART_LIBRARY_DIR}/")


if __name__ == "__main__":
    main()
