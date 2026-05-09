from __future__ import annotations

from grafted.core.enums import AttackSurface
from grafted.core.schemas import TestSpec


class SurfaceCatalogRouter:
    """Maps (AttackSurface, technique_family) → list[TestSpec].

    Pre-loaded from user-provided catalogs. Falls back to empty list
    if no catalog registered for a surface.
    """

    def __init__(self) -> None:
        self._catalog: dict[AttackSurface, list[TestSpec]] = {}

    def register(self, surface: AttackSurface, specs: list[TestSpec]) -> None:
        existing = self._catalog.get(surface, [])
        self._catalog[surface] = existing + specs

    def select(
        self,
        surface: AttackSurface,
        technique_hint: str | None = None,
        top_k: int = 3,
    ) -> list[TestSpec]:
        """Return top_k TestSpecs for surface, ranked by technique match."""
        candidates = list(self._catalog.get(surface, []))
        if not candidates:
            return []
        if technique_hint:
            exact = [s for s in candidates if s.technique_family == technique_hint]
            rest = [s for s in candidates if s.technique_family != technique_hint]
            candidates = exact + rest
        return candidates[:top_k]

    @property
    def known_surfaces(self) -> list[AttackSurface]:
        return list(self._catalog.keys())
