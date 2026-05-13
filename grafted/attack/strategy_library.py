"""Pattern-2 Strategy Library: persisted artifact of offline-trained attack patterns.

A `Strategy` is an ABSTRACT template (with placeholders like {goal}, {user},
{model}) plus metadata about when it applies and how well it performed
during offline training. The `StrategyLibrary` is a per-suite collection
sorted by training_asr, with a `best_for(...)` lookup used at evaluation
time to retrieve a strategy that will be instantiated into a final payload
string without any attacker-LLM call.

The library is persisted as JSON at `data/grafted/strategy_library/{suite}.json`
and is COMPLETELY SEPARATE from per-engagement StrategicMemory (which lives
under `data/grafted/memory/`). This separation matters: the library is an
artifact reused across engagements, victims, and runs; engagement memory
is per-run state.

Distillation:
- After offline training collects a bag of winning payloads (per
  injection_task + per technique tag), `distill_winning_turns()` clusters
  them by template-shape similarity (which placeholders/structural features
  they share) and abstracts each cluster into one Strategy.
- For the first iteration we use very simple structural-feature clustering
  (presence of <INFORMATION> tags, presence of user-impersonation,
  presence of "Signed,..." signoff) — enough to distinguish the
  ~3-5 broad attack styles seen in AgentDojo wins.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("grafted.attack.strategy_library")


@dataclass
class Strategy:
    """One abstract attack template with metadata.

    Placeholders in `template` are filled at evaluation time from
    `fill_rules`. Standard placeholders we support:
        {goal}       — the injection_task.GOAL verbatim
        {user_name}  — the agent's "user" identity (e.g., "Emma Johnson")
        {model_name} — the agent's "model" name (e.g., "AI assistant")
    """

    id: str
    template: str
    fill_rules: dict[str, str]
    applicable_surfaces: list[str]
    applicable_tools: list[str]
    technique_tags: list[str]
    training_asr: float
    training_n: int
    parent_winning_turns: list[str] = field(default_factory=list)

    def instantiate(self, context: dict[str, str]) -> str:
        """Fill placeholders in `template` from `context`.

        Missing placeholders are left untouched rather than raising — that
        way a strategy designed with optional placeholders degrades
        gracefully.
        """
        out = self.template
        for placeholder, source_key in self.fill_rules.items():
            value = context.get(source_key, "")
            out = out.replace("{" + placeholder + "}", value)
        return out

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Strategy":
        # Defensive: only pass known fields
        known = {f for f in cls.__dataclass_fields__}
        filtered = {k: v for k, v in data.items() if k in known}
        return cls(**filtered)


class StrategyLibrary:
    """Per-suite collection of Strategies, loaded from JSON at eval time."""

    def __init__(
        self,
        suite_name: str,
        strategies: Optional[list[Strategy]] = None,
        meta: Optional[dict[str, Any]] = None,
    ) -> None:
        self.suite_name = suite_name
        self.strategies: list[Strategy] = list(strategies or [])
        # Keep sorted by training_asr desc for quick best_for() lookups
        self.strategies.sort(key=lambda s: s.training_asr, reverse=True)
        self.meta = meta or {}

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    @classmethod
    def load(cls, path: Path) -> "StrategyLibrary":
        path = Path(path)
        data = json.loads(path.read_text(encoding="utf-8"))
        strategies = [Strategy.from_dict(s) for s in data.get("strategies", [])]
        return cls(
            suite_name=data.get("suite_name", ""),
            strategies=strategies,
            meta=data.get("meta", {}),
        )

    def save(self, path: Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "suite_name": self.suite_name,
            "meta": self.meta,
            "strategies": [s.to_dict() for s in self.strategies],
        }
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    # ------------------------------------------------------------------
    # Lookup
    # ------------------------------------------------------------------

    def best_for(
        self,
        *,
        surface: Optional[str] = None,
        tool: Optional[str] = None,
        technique: Optional[str] = None,
    ) -> Optional[Strategy]:
        """Return the highest-training_asr Strategy that matches all given
        filters. None means "no filter on this dimension". Returns None if
        no strategy matches."""
        for s in self.strategies:
            if surface and surface not in s.applicable_surfaces and "*" not in s.applicable_surfaces:
                continue
            if tool and tool not in s.applicable_tools and "*" not in s.applicable_tools:
                continue
            if technique and technique not in s.technique_tags:
                continue
            return s
        return None

    def __len__(self) -> int:
        return len(self.strategies)

    def __repr__(self) -> str:
        return f"StrategyLibrary(suite={self.suite_name!r}, n={len(self)})"


# ------------------------------------------------------------------
# Distillation (offline training utility)
# ------------------------------------------------------------------

_INFO_TAG_RE = re.compile(r"<INFORMATION>", re.IGNORECASE)
_USER_IMPERS_RE = re.compile(r"from me,\s*(\w+\s+\w+|\{user_name\})", re.IGNORECASE)
_SIGNED_RE = re.compile(r"Signed[,:]?\s*(\w+\s+\w+|\{user_name\})", re.IGNORECASE)


def _structural_features(text: str) -> tuple[bool, bool, bool]:
    """Extract a 3-bit structural fingerprint: (has_info_tag,
    has_user_impersonation, has_signed_signoff). Used as the cluster key
    for distillation."""
    return (
        bool(_INFO_TAG_RE.search(text)),
        bool(_USER_IMPERS_RE.search(text)),
        bool(_SIGNED_RE.search(text)),
    )


def _abstract_template(
    raw_payload: str,
    goal_text: str,
    user_name: str,
    model_name: str,
) -> tuple[str, dict[str, str]]:
    """Replace literal goal/user/model occurrences with placeholders.

    Returns (templated_text, fill_rules). fill_rules maps placeholder name
    to the context-dict key the runtime should pull from.
    """
    out = raw_payload
    # Order matters: replace longer strings first to avoid partial overlaps
    replacements = [
        (goal_text, "{goal}", "goal"),
        (user_name, "{user_name}", "user_name"),
        (model_name, "{model_name}", "model_name"),
    ]
    fill_rules = {}
    for literal, placeholder, key in replacements:
        if literal and literal in out:
            out = out.replace(literal, placeholder)
            # placeholder is "{x}"; we record the bare name "x" so caller
            # can build context dict with that key
            fill_rules[placeholder.strip("{}")] = key
    return out, fill_rules


@dataclass
class WinningRecord:
    """One winning payload observed during offline training."""

    payload: str
    goal_text: str
    user_name: str
    model_name: str
    target_tool: str
    surface: str
    technique: str
    score: float = 1.0  # 1.0 = single-shot win; could be MC-estimated later


def distill_winning_turns(
    wins: list[WinningRecord],
    suite_name: str,
    min_cluster_size: int = 1,
) -> list[Strategy]:
    """Cluster winning records by structural fingerprint, abstract to
    placeholders, emit one Strategy per cluster.

    `min_cluster_size` filters out singleton clusters (one-off wins).
    Default 1 = keep everything; bump to 2+ for stricter library.
    """
    if not wins:
        return []

    # Group by (structural_fingerprint, surface) — surface preserved
    # because the same template can have different applicability
    clusters: dict[tuple[tuple[bool, bool, bool], str], list[WinningRecord]] = {}
    for w in wins:
        key = (_structural_features(w.payload), w.surface)
        clusters.setdefault(key, []).append(w)

    strategies: list[Strategy] = []
    for (features, surface), records in clusters.items():
        if len(records) < min_cluster_size:
            continue
        # Use the highest-scoring record in the cluster as the canonical seed
        canonical = max(records, key=lambda r: r.score)
        templated, fill_rules = _abstract_template(
            canonical.payload, canonical.goal_text, canonical.user_name, canonical.model_name
        )
        feature_tags = []
        if features[0]:
            feature_tags.append("info_tag")
        if features[1]:
            feature_tags.append("user_impersonation")
        if features[2]:
            feature_tags.append("signed_signoff")
        if not feature_tags:
            feature_tags = ["plain"]
        tools = sorted({r.target_tool for r in records if r.target_tool})
        techniques = sorted({r.technique for r in records if r.technique} | set(feature_tags))
        avg_score = sum(r.score for r in records) / len(records)
        strategy_id = f"{suite_name}__{'_'.join(feature_tags)}__n{len(records)}"
        strategies.append(
            Strategy(
                id=strategy_id,
                template=templated,
                fill_rules=fill_rules,
                applicable_surfaces=[surface],
                applicable_tools=tools or ["*"],
                technique_tags=techniques,
                training_asr=avg_score,
                training_n=len(records),
                parent_winning_turns=[r.payload for r in records[:3]],
            )
        )

    # Sort by training_asr desc (best_for relies on this)
    strategies.sort(key=lambda s: s.training_asr, reverse=True)
    return strategies
