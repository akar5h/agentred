from __future__ import annotations

import json

import pytest

from harness.attack.catalog.loader import iter_attacks, load_catalog, load_test_specs
from harness.core.enums import AttackSurface, VesselKind
from harness.core.exceptions import CatalogError


def _write_catalog(tmp_path, payload: dict) -> str:
    p = tmp_path / "catalog.json"
    p.write_text(json.dumps(payload), encoding="utf-8")
    return str(p)


def _base_catalog() -> dict:
    return {
        "suite_id": "direct_chat_injection_v1",
        "version": "1.0.0",
        "attacks": [
            {
                "id": "A-01",
                "category": "test",
                "severity": "low",
                "turns": ["hello"],
                "owasp": ["LLM01"],
                "atlas": ["AML.TA0001"],
                "success_criteria": "none",
                "oracle_codes": ["canary_exfiltrated"],
            }
        ],
    }


def test_load_catalog_returns_attacks_list(tmp_path) -> None:
    path = _write_catalog(tmp_path, _base_catalog())
    loaded = load_catalog(path)
    assert isinstance(loaded["attacks"], list)
    assert len(loaded["attacks"]) == 1


def test_load_catalog_raises_on_missing_required_key(tmp_path) -> None:
    payload = _base_catalog()
    del payload["attacks"][0]["id"]
    path = _write_catalog(tmp_path, payload)
    with pytest.raises(CatalogError):
        load_catalog(path)


def test_load_catalog_raises_on_empty_attacks(tmp_path) -> None:
    payload = _base_catalog()
    payload["attacks"] = []
    path = _write_catalog(tmp_path, payload)
    with pytest.raises(CatalogError):
        load_catalog(path)


def test_iter_attacks_filters_by_id(tmp_path) -> None:
    payload = _base_catalog()
    payload["attacks"].append(
        {
            "id": "A-02",
            "category": "test",
            "severity": "low",
            "turns": ["hello2"],
            "owasp": ["LLM01"],
            "atlas": ["AML.TA0001"],
            "success_criteria": "none",
            "oracle_codes": [],
        }
    )
    path = _write_catalog(tmp_path, payload)
    loaded = load_catalog(path)
    out = list(iter_attacks(loaded, ids={"A-02"}))
    assert len(out) == 1
    assert out[0]["id"] == "A-02"


@pytest.mark.parametrize(
    "suite_id,expected",
    [
        ("direct_chat_injection_v1", AttackSurface.DIRECT_CHAT),
        ("indirect_upload_injection_v1", AttackSurface.INDIRECT_UPLOAD),
        ("memory_poisoning_v1", AttackSurface.MEMORY_POISONING),
        ("tool_poisoning_v1", AttackSurface.TOOL_POISONING),
        ("tool_misuse_v1", AttackSurface.TOOL_POISONING),
        ("agent_exfiltration_v1", AttackSurface.DATA_EXTRACTION),
    ],
)
def test_load_test_specs_infers_attack_surface(tmp_path, suite_id, expected) -> None:
    payload = _base_catalog()
    payload["suite_id"] = suite_id
    path = _write_catalog(tmp_path, payload)
    _, specs = load_test_specs(path)
    assert len(specs) == 1
    assert specs[0].attack_surface == expected


def test_load_test_specs_creates_vessel_specs_from_uploads(tmp_path) -> None:
    payload = _base_catalog()
    payload["suite_id"] = "indirect_upload_injection_v1"
    payload["attacks"][0]["uploads"] = [{"fixture": "fixtures/a.md", "render": True}]
    path = _write_catalog(tmp_path, payload)

    _, specs = load_test_specs(path)
    assert len(specs[0].vessels) == 1
    vessel = specs[0].vessels[0]
    assert vessel.kind == VesselKind.UPLOADED_DOCUMENT
    assert vessel.fixture_path == "fixtures/a.md"
    assert vessel.render_template is True


def test_load_test_specs_reads_chain_fields(tmp_path) -> None:
    payload = _base_catalog()
    payload["attacks"][0]["chain_mode"] = True
    payload["attacks"][0]["max_chain_turns"] = 5
    path = _write_catalog(tmp_path, payload)

    _, specs = load_test_specs(path)
    assert specs[0].chain_mode is True
    assert specs[0].max_chain_turns == 5
