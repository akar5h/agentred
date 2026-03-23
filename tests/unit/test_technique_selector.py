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


def test_all_ids_returns_fourteen_techniques():
    sel = _selector()
    ids = sel.all_ids()
    assert len(ids) == 14
    assert "direct_request" in ids
    assert "technical_camouflage" in ids
    assert "opinion_seeking" in ids
    assert "sink_confirmation_probe" in ids


def test_next_for_objective_returns_generic_first():
    """Generic techniques (no objectives filter) match first due to lower order."""
    sel = _selector()
    tid, _ = sel.next_for_objective("score_manipulation", "direct_chat", set())
    assert tid == "direct_request"  # order=0, no filter → matches everything


def test_next_for_objective_reaches_specific_after_generics():
    sel = _selector()
    generics = {"direct_request", "authority_escalation", "indirect_framing",
                "foot_in_door", "roleplay_embedding", "technical_camouflage"}
    tid, hint = sel.next_for_objective("score_manipulation", "direct_chat", generics)
    assert tid == "opinion_seeking"
    assert "opinion" in hint.lower()


def test_next_for_objective_filters_by_surface():
    sel = _selector()
    generics = {"direct_request", "authority_escalation", "indirect_framing",
                "foot_in_door", "roleplay_embedding", "technical_camouflage"}
    tid, _ = sel.next_for_objective("tool_hijack", "tool_schema_enumeration", generics)
    assert tid == "tool_parameter_probing"


def test_next_for_objective_skips_tried():
    sel = _selector()
    tried = {"direct_request", "authority_escalation", "indirect_framing",
             "foot_in_door", "roleplay_embedding", "technical_camouflage",
             "opinion_seeking", "passive_confirmation"}
    tid, _ = sel.next_for_objective("score_manipulation", "direct_chat", tried)
    assert tid == "gradual_benign_escalation"


def test_next_for_objective_returns_empty_when_all_tried():
    sel = _selector()
    all_ids = set(sel.all_ids())
    tid, hint = sel.next_for_objective("score_manipulation", "direct_chat", all_ids)
    assert tid == ""
    assert hint == ""


def test_hints_for_context_returns_matching_hints():
    sel = _selector()
    hints = sel.hints_for_context("memory_poisoning", "direct_chat")
    assert len(hints) >= 1
    ids = [h[0] for h in hints]
    assert "memory_preference_injection" in ids


def test_hints_for_context_respects_limit():
    sel = _selector()
    hints = sel.hints_for_context("score_manipulation", "direct_chat", limit=2)
    assert len(hints) <= 2


def test_hints_for_context_returns_only_generics_for_no_match():
    """Unknown objective/surface still returns generic techniques."""
    sel = _selector()
    hints = sel.hints_for_context("nonexistent", "nonexistent")
    # Only generics (no objectives/surfaces tags) match
    ids = [h[0] for h in hints]
    assert "opinion_seeking" not in ids
    assert "memory_preference_injection" not in ids
    assert len(hints) > 0  # generics still present
