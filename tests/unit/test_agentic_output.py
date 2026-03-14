"""Tests for AgenticCycleOutput parsing in MuzzleOrchestrator."""
from __future__ import annotations

import json

import pytest

from harness.core.schemas import AgenticCycleOutput


class TestAgenticCycleOutputSchema:
    """Test the Pydantic model itself."""

    def test_valid_json(self):
        raw = json.dumps({
            "cycle": 1,
            "surfaces_found": ["direct_chat", "tool_calling"],
            "specs_executed": 3,
            "hits": [{"scenario_id": "s1", "oracle_codes": ["prompt_leak"]}],
        })
        out = AgenticCycleOutput.model_validate_json(raw)
        assert out.cycle == 1
        assert out.surfaces_found == ["direct_chat", "tool_calling"]
        assert out.specs_executed == 3
        assert len(out.hits) == 1

    def test_defaults(self):
        out = AgenticCycleOutput(cycle=0)
        assert out.surfaces_found == []
        assert out.specs_executed == 0
        assert out.hits == []
        assert out.error == ""

    def test_extra_keys_allowed(self):
        raw = json.dumps({
            "cycle": 2,
            "surfaces_found": [],
            "specs_executed": 0,
            "hits": [],
            "unexpected_key": "ignored",
        })
        out = AgenticCycleOutput.model_validate_json(raw)
        assert out.cycle == 2


class TestParseAgenticOutput:
    """Test the _parse_agentic_output method on MuzzleOrchestrator."""

    @pytest.fixture
    def parser(self):
        """Create a minimal MuzzleOrchestrator just for the parser method."""
        from unittest.mock import MagicMock
        from harness.campaign.muzzle_orchestrator import MuzzleOrchestrator

        # Access the unbound method
        return MuzzleOrchestrator._parse_agentic_output

    def _call(self, parser, raw: str, cycle: int = 1) -> AgenticCycleOutput:
        """Call the parser as an unbound method with a dummy self."""
        from unittest.mock import MagicMock
        return parser(MagicMock(), raw, cycle)

    def test_path1_strict_json(self, parser):
        raw = json.dumps({
            "cycle": 1,
            "surfaces_found": ["direct_chat"],
            "specs_executed": 2,
            "hits": [],
        })
        out = self._call(parser, raw)
        assert out.cycle == 1
        assert out.surfaces_found == ["direct_chat"]
        assert out.specs_executed == 2

    def test_path1_with_markdown_fences(self, parser):
        raw = '```json\n{"cycle": 3, "surfaces_found": ["tool_calling"], "specs_executed": 1, "hits": []}\n```'
        out = self._call(parser, raw, cycle=3)
        assert out.cycle == 3
        assert out.surfaces_found == ["tool_calling"]

    def test_path2_partial_json(self, parser):
        raw = json.dumps({
            "cycle": 2,
            "surfaces_found": ["memory_state"],
            "specs_executed": 5,
            "hits": [{"status": "Success"}],
            "extra_field": True,
        })
        out = self._call(parser, raw, cycle=2)
        assert out.cycle == 2
        assert out.specs_executed == 5

    def test_path3_unstructured_text(self, parser):
        raw = (
            "I explored the victim and found direct_chat and tool_calling surfaces. "
            "Specs executed: 4 specs were run."
        )
        out = self._call(parser, raw, cycle=5)
        assert out.cycle == 5
        assert "direct_chat" in out.surfaces_found
        assert "tool_calling" in out.surfaces_found
        assert out.error == "parsed_via_regex_fallback"

    def test_path3_empty_output(self, parser):
        out = self._call(parser, "", cycle=0)
        assert out.cycle == 0
        assert out.error == "empty_output"

    def test_path3_specs_regex(self, parser):
        raw = "The exploration found memory_poisoning. Specs executed: 7 in total."
        out = self._call(parser, raw, cycle=1)
        assert out.specs_executed == 7
        assert "memory_poisoning" in out.surfaces_found
