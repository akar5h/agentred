"""Unit tests for TechniqueSelector."""
from __future__ import annotations

from harness.attack.technique_selector import TechniqueSelector


def _selector() -> TechniqueSelector:
    return TechniqueSelector()


def test_next_returns_next_technique_after_direct_request():
    sel = _selector()
    next_id, hint = sel.next("direct_request", {"direct_request"})
    assert next_id == "authority_escalation"
    assert isinstance(hint, str)


def test_next_skips_already_tried():
    sel = _selector()
    tried = {"direct_request", "authority_escalation"}
    next_id, _ = sel.next("direct_request", tried)
    assert next_id == "indirect_framing"


def test_next_returns_empty_when_palette_exhausted():
    sel = _selector()
    all_ids = set(sel.all_ids())
    next_id, hint = sel.next("technical_camouflage", all_ids)
    assert next_id == ""
    assert hint == ""


def test_next_advances_from_middle_of_palette():
    sel = _selector()
    tried = {"direct_request", "authority_escalation", "indirect_framing"}
    next_id, _ = sel.next("indirect_framing", tried)
    assert next_id == "foot_in_door"


def test_framing_hint_returns_string_for_known_id():
    sel = _selector()
    hint = sel.framing_hint("authority_escalation")
    assert len(hint) > 0


def test_framing_hint_returns_empty_for_unknown_id():
    sel = _selector()
    assert sel.framing_hint("nonexistent_technique") == ""


def test_all_ids_returns_six_techniques():
    sel = _selector()
    ids = sel.all_ids()
    assert len(ids) == 6
    assert "direct_request" in ids
    assert "technical_camouflage" in ids
