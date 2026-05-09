from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Iterator, Optional, Set, Tuple, Union

logger = logging.getLogger("grafted.attack.catalog.loader")

from grafted.attack.catalog.validator import validate_catalog
from grafted.core.enums import AttackSurface, OracleCode, VesselKind
from grafted.core.schemas import TestSpec, VesselSpec


def load_catalog(catalog_path: Union[str, Path]) -> dict[str, Any]:
    raw = Path(catalog_path)
    if raw.is_absolute():
        path = raw
    else:
        project_root = Path(__file__).resolve().parents[3]
        candidates = [
            Path.cwd() / raw,
            project_root / raw,
        ]
        path = next((p for p in candidates if p.exists()), candidates[0])

    if not path.exists():
        raise FileNotFoundError(f"Catalog not found: {raw}. Tried from {Path.cwd()}.")

    payload = json.loads(path.read_text(encoding="utf-8"))
    validate_catalog(payload, catalog_path=str(path))

    attacks = payload.get("attacks", [])
    for attack in attacks:
        expected = attack.get("expected")
        if expected is None:
            attack["expected"] = {"ideal_status": "Blocked"}
        elif not isinstance(expected, dict):
            attack["expected"] = {"ideal_status": str(expected)}

    return payload


def iter_attacks(
    catalog: dict[str, Any],
    *,
    ids: Optional[Set[str]] = None,
    categories: Optional[Set[str]] = None,
) -> Iterator[dict[str, Any]]:
    for attack in catalog.get("attacks", []):
        attack_id = str(attack.get("id", "")).strip()
        if ids and attack_id not in ids:
            continue
        category = str(attack.get("category", "")).strip()
        if categories and category not in categories:
            continue
        yield attack


def _infer_attack_surface(catalog: dict[str, Any]) -> AttackSurface:
    suite = str(catalog.get("suite_id", ""))
    if suite.startswith("indirect_upload"):
        return AttackSurface.INDIRECT_UPLOAD
    if suite.startswith("memory_poisoning"):
        return AttackSurface.MEMORY_POISONING
    if suite.startswith("tool_poisoning") or suite.startswith("tool_misuse"):
        return AttackSurface.TOOL_POISONING
    if suite.startswith("agent_exfiltration"):
        return AttackSurface.DATA_EXTRACTION
    return AttackSurface.DIRECT_CHAT


def _resolve_attack_surface(attack: dict[str, Any], catalog: dict[str, Any]) -> AttackSurface:
    """Use explicit attack_surface from attack or catalog, fall back to heuristic."""
    for source in (attack, catalog):
        raw = source.get("attack_surface")
        if raw:
            try:
                return AttackSurface(str(raw))
            except ValueError:
                pass
    return _infer_attack_surface(catalog)


def _attack_to_spec(attack: dict[str, Any], catalog: dict[str, Any]) -> TestSpec:
    vessel_specs: list[VesselSpec] = []
    for upload in attack.get("uploads", []):
        vessel_specs.append(
            VesselSpec(
                kind=VesselKind.UPLOADED_DOCUMENT,
                fixture_path=upload["fixture"],
                render_template=bool(upload.get("render", True)),
            )
        )

    oracle_codes: list[OracleCode] = []
    for raw_code in attack.get("oracle_codes", []):
        code = str(raw_code)
        try:
            oracle_codes.append(OracleCode(code.lower()))
        except ValueError:
            try:
                oracle_codes.append(OracleCode(code))
            except ValueError:
                logger.debug("Skipping invalid oracle code %r in catalog", code)
                continue

    return TestSpec(
        scenario_id=str(attack.get("id", "")),
        suite_id=str(catalog.get("suite_id", "")),
        turns=[str(t) for t in attack.get("turns", [])],
        prelude_turns=[str(t) for t in attack.get("prelude_turns", [])],
        vessels=vessel_specs,
        oracle_codes=oracle_codes,
        expected=attack.get("expected", {}),
        adaptive=bool(attack.get("adaptive", False)),
        category=str(attack.get("category", "")),
        severity=str(attack.get("severity", "")),
        owasp=[str(x) for x in attack.get("owasp", [])],
        atlas=[str(x) for x in attack.get("atlas", [])],
        objective=str(attack.get("objective", "")),
        success_criteria=str(attack.get("success_criteria", "")),
        attack_surface=_resolve_attack_surface(attack, catalog),
        technique_family=str(attack.get("technique_family", "")),
        chain_mode=bool(attack.get("chain_mode", False)),
        max_chain_turns=int(attack.get("max_chain_turns", 8)),
    )


def load_test_specs(catalog_path: Union[str, Path]) -> Tuple[dict[str, Any], list[TestSpec]]:
    catalog = load_catalog(catalog_path)
    specs = [_attack_to_spec(attack, catalog) for attack in catalog["attacks"]]
    return catalog, specs
