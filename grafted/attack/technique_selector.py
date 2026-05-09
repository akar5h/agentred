"""Technique palette selector for guardrail-adaptive attacking.

When an attack is BLOCKED, TechniqueSelector picks the next framing technique
from the ordered palette. This implements the inner adaptation loop:
- Outer loop: bandit selects which surface to focus on
- Inner loop: TechniqueSelector switches technique when guardrails fire
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)


_DEFAULT_LIBRARY = Path(__file__).parent / "technique_library.json"


class TechniqueSelector:
    def __init__(self, library_path: Optional[str] = None):
        path = Path(library_path) if library_path else _DEFAULT_LIBRARY
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            self._techniques: list[dict] = sorted(raw, key=lambda t: t.get("order", 99))
        except Exception as exc:
            log.warning("Failed to load technique library from %s: %s", path, exc)
            self._techniques = []
        self._by_id: dict[str, dict] = {t["id"]: t for t in self._techniques}

    def next(self, current_id: str, tried: set[str]) -> tuple[str, str]:
        """Return (next_technique_id, framing_hint) or ("", "") if palette exhausted.

        Args:
            current_id: technique_id of the last attempted attack
            tried: set of technique_ids already attempted for this spec
        """
        current_order = self._by_id.get(current_id, {}).get("order", -1)
        for technique in self._techniques:
            if technique["id"] in tried:
                continue
            if technique.get("order", 99) > current_order:
                return technique["id"], technique.get("framing_hint", "")
        return "", ""

    def framing_hint(self, technique_id: str) -> str:
        return self._by_id.get(technique_id, {}).get("framing_hint", "")

    def all_ids(self) -> list[str]:
        return [t["id"] for t in self._techniques]

    def next_for_objective(
        self, objective: str, surface: str, tried: set[str]
    ) -> tuple[str, str]:
        """Return the next untried technique matching objective + surface."""
        for technique in self._techniques:
            if technique["id"] in tried:
                continue
            objectives = technique.get("objectives", [])
            surfaces = technique.get("surfaces", [])
            if objectives and objective not in objectives:
                continue
            if surfaces and surface not in surfaces:
                continue
            return technique["id"], technique.get("framing_hint", "")
        return "", ""

    def hints_for_context(
        self, objective: str, surface: str, limit: int = 4
    ) -> list[tuple[str, str]]:
        """Return (id, framing_hint) pairs matching objective + surface.

        Prioritises techniques with explicit objectives/surfaces tags over
        generic techniques that match everything.
        """
        specific: list[tuple[str, str]] = []
        generic: list[tuple[str, str]] = []
        for technique in self._techniques:
            objectives = technique.get("objectives", [])
            surfaces = technique.get("surfaces", [])
            if objectives and objective not in objectives:
                continue
            if surfaces and surface not in surfaces:
                continue
            hint = technique.get("framing_hint", "")
            if not hint:
                continue
            if objectives or surfaces:
                specific.append((technique["id"], hint))
            else:
                generic.append((technique["id"], hint))
        return (specific + generic)[:limit]
