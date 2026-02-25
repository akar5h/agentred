"""Tests for harness.memory.working — WorkingMemory, VesselOutcome."""
from __future__ import annotations

from harness.memory.working import VesselOutcome, WorkingMemory


class TestVesselOutcome:
    def test_defaults(self):
        vo = VesselOutcome(vessel_kind="direct_prompt", technique="grafted_direct_prompt", status="Success")
        assert vo.oracle_codes == []
        assert vo.turn_count == 0


class TestWorkingMemory:
    def test_initial_state(self):
        wm = WorkingMemory(cycle=0)
        assert wm.cycle == 0
        assert wm.surfaces_discovered == []
        assert wm.vessels_tried == []
        assert wm.current_hypothesis == ""
        assert wm.notes == []

    def test_record_surface(self):
        wm = WorkingMemory()
        wm.record_surface("direct_chat")
        wm.record_surface("memory_poisoning")
        assert wm.surfaces_discovered == ["direct_chat", "memory_poisoning"]

    def test_record_surface_deduplicates(self):
        wm = WorkingMemory()
        wm.record_surface("direct_chat")
        wm.record_surface("direct_chat")
        assert wm.surfaces_discovered == ["direct_chat"]

    def test_record_surface_ignores_empty(self):
        wm = WorkingMemory()
        wm.record_surface("")
        assert wm.surfaces_discovered == []

    def test_record_vessel_outcome(self):
        wm = WorkingMemory()
        wm.record_vessel_outcome(
            vessel_kind="direct_prompt",
            technique="grafted_direct_prompt",
            status="Success",
            oracle_codes=["prompt_leak"],
            turn_count=3,
        )
        assert len(wm.vessels_tried) == 1
        vo = wm.vessels_tried[0]
        assert vo.vessel_kind == "direct_prompt"
        assert vo.status == "Success"
        assert vo.oracle_codes == ["prompt_leak"]
        assert vo.turn_count == 3

    def test_set_hypothesis(self):
        wm = WorkingMemory()
        wm.set_hypothesis("Victim leaks system prompt when asked about tools")
        assert wm.current_hypothesis == "Victim leaks system prompt when asked about tools"

    def test_add_note(self):
        wm = WorkingMemory()
        wm.add_note("Victim refused file upload")
        wm.add_note("Tool listing revealed internal tools")
        assert len(wm.notes) == 2

    def test_summarize_for_carry_forward(self):
        wm = WorkingMemory(cycle=1)
        wm.record_surface("direct_chat")
        wm.record_vessel_outcome("direct_prompt", "grafted_direct_prompt", "Success")
        wm.set_hypothesis("Prompt leak via direct chat")
        summary = wm.summarize_for_carry_forward()
        assert "Cycle 1" in summary
        assert "direct_chat" in summary
        assert "Wins: 1" in summary
        assert "Prompt leak via direct chat" in summary

    def test_summarize_empty(self):
        wm = WorkingMemory(cycle=0)
        summary = wm.summarize_for_carry_forward()
        assert "Cycle 0" in summary

    def test_reset_creates_fresh_with_carry_forward(self):
        wm = WorkingMemory(cycle=0)
        wm.record_surface("direct_chat")
        wm.set_hypothesis("test hypothesis")

        new_wm = wm.reset(new_cycle=1)
        assert new_wm.cycle == 1
        assert new_wm.surfaces_discovered == []
        assert new_wm.vessels_tried == []
        assert new_wm.current_hypothesis == ""
        assert len(new_wm.notes) == 1
        assert "[carry-forward]" in new_wm.notes[0]

    def test_reset_preserves_nothing_from_old(self):
        wm = WorkingMemory(cycle=0)
        wm.record_surface("memory_poisoning")
        wm.record_vessel_outcome("memory_entry", "memory_poisoning", "Blocked")
        new_wm = wm.reset(new_cycle=1)
        assert "memory_poisoning" not in new_wm.surfaces_discovered
        assert len(new_wm.vessels_tried) == 0
