from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from harness.core.enums import AttackSurface, FailureReason, OracleCode, Status, VesselKind


class _HarnessBaseModel(BaseModel):
    model_config = ConfigDict(extra="allow")


class VesselSpec(_HarnessBaseModel):
    kind: VesselKind
    delivery_field: str = "message"
    fixture_path: Optional[str] = None
    render_template: bool = True


class TestSpec(_HarnessBaseModel):
    scenario_id: str
    suite_id: str
    turns: list[str]
    prelude_turns: list[str] = Field(default_factory=list)
    vessels: list[VesselSpec] = Field(default_factory=list)
    oracle_codes: list[OracleCode] = Field(default_factory=list)
    expected: dict = Field(default_factory=dict)
    adaptive: bool = False
    category: str = ""
    severity: str = ""
    owasp: list[str] = Field(default_factory=list)
    atlas: list[str] = Field(default_factory=list)
    objective: str = ""
    success_criteria: str = ""
    attack_surface: Optional[AttackSurface] = None
    technique_family: str = ""


class JudgeResult(_HarnessBaseModel):
    run_id: str
    scenario_id: str
    suite_id: str
    rep: int = 1
    status: Status
    failure_reason: Optional[FailureReason] = None
    suggested_variant: str = ""
    reflection_notes: list[str] = Field(default_factory=list)
    attack_surface: Optional[AttackSurface] = None
    technique_family: str = ""
    hard_flags: dict[str, bool] = Field(default_factory=dict)
    soft_success: bool = False
    soft_score: float = 0.0
    soft_findings: list[dict] = Field(default_factory=list)
    write_delta: int = 0
    canary_token: str = ""
    session_id: str = ""
    turn_count: int = 0
    final_response: str = ""
    duration_ms: int = 0
    error: str = ""
    notes: list[str] = Field(default_factory=list)


class TelemetryEvent(_HarnessBaseModel):
    run_id: str
    scenario_id: str
    suite_id: str
    event_type: str
    turn_index: int = -1
    content: str = ""
    canary_token: str = ""
    meta: dict = Field(default_factory=dict)
    timestamp_iso: str = ""


class TargetProfile(_HarnessBaseModel):
    known_internal_tool_names: list[str] = Field(default_factory=list)
    known_internal_state_keys: list[str] = Field(
        default_factory=lambda: ["thread_id", "checkpoint", "configurable"]
    )


class RunConfig(_HarnessBaseModel):
    catalog_path: str
    base_url: str = "http://localhost:8000"
    target_mode: str = "chat"
    runs_per_scenario: int = 1
    timeout_seconds: float = 120.0
    adaptive: bool = False
    attacker_model: str = "moonshotai/kimi-k2-0905"
    attacker_fallback_model: str = "moonshotai/kimi-k2-thinking"
    attacker_endpoint: str = "https://openrouter.ai/api/v1/chat/completions"
    attacker_api_key_env: str = "OPENROUTER_API_KEY"
    attacker_max_rpm: int = 6
    attacker_cooldown_seconds: float = 15.0
    analyst_enabled: bool = True
    analyst_model: str = "anthropic/claude-sonnet-4-6"
    analyst_endpoint: str = "https://openrouter.ai/api/v1/chat/completions"
    analyst_api_key_env: str = "OPENROUTER_API_KEY"
    scenario_filter: list[str] = Field(default_factory=list)
    run_dir: str = ""
    max_cost_usd: float = 10.0
    target_profile_path: str = ""
    # MUZZLE orchestrator fields (Phase E)
    engagement_id: str = ""
    max_muzzle_cycles: int = 3
    top_k_vessels: int = 3
    objective_goals: list[str] = Field(default_factory=lambda: ["prompt_exfil", "state_exfil"])
    no_muzzle: bool = False


# ---------------------------------------------------------------------------
# Phase E schemas — Explorer / Grafter / ObjectiveReplay / MUZZLE memory
# ---------------------------------------------------------------------------


class FindingMemory(_HarnessBaseModel):
    scenario_id: str
    attack_surface: str
    vessel_kind: str
    technique_family: str
    oracle_codes_fired: list[str] = Field(default_factory=list)
    winning_turn: str
    canary_confirmed: bool = False
    cycle: int = 0


class ExplorationTask(_HarnessBaseModel):
    task_id: str
    description: str
    turns: list[str]
    expected_actions: list[str] = Field(default_factory=list)


class TraceStep(_HarnessBaseModel):
    turn_index: int
    message_sent: str
    response: str
    docs_before: list[dict] = Field(default_factory=list)
    docs_after: list[dict] = Field(default_factory=list)
    duration_ms: int = 0
    inferred_actions: list[str] = Field(default_factory=list)


class ExplorationTrace(_HarnessBaseModel):
    task_id: str
    session_id: str
    steps: list[TraceStep]
    target_base_url: str = ""


class ExecutionStep(_HarnessBaseModel):
    step_type: str
    artifact_ref: Optional[str] = None
    content_preview: str = ""
    turn_index: int = 0


class SummarizedTrace(_HarnessBaseModel):
    trace_id: str
    steps: list[ExecutionStep]
    inferred_surfaces: list[str] = Field(default_factory=list)


class VesselCandidate(_HarnessBaseModel):
    vessel_kind: VesselKind
    delivery_field: str
    exploit_method: str
    exploitability_score: float = 0.0
    saliency_score: float = 0.0
    surface_budget_bytes: int = -1
    privilege_required: str = "public"
    source_step_index: int = 0


class CatalogEntry(_HarnessBaseModel):
    entry_id: str
    suite_id: str
    attack_surface: str
    technique_family: str
    vessel_kinds: list[str] = Field(default_factory=list)
    turns: list[str] = Field(default_factory=list)
    prelude_turns: list[str] = Field(default_factory=list)
    oracle_codes: list[str] = Field(default_factory=list)
    severity: str = "medium"
    description: str = ""


class AttackCatalogFile(_HarnessBaseModel):
    catalog_id: str
    version: str
    entries: list[CatalogEntry] = Field(default_factory=list)


class CatalogMatchResult(_HarnessBaseModel):
    matched_entries: list[CatalogEntry] = Field(default_factory=list)
    coverage_gaps: list[VesselCandidate] = Field(default_factory=list)
    depth_gaps: list[CatalogEntry] = Field(default_factory=list)
    match_confidence: dict[str, float] = Field(default_factory=dict)


class CatalogEnrichmentProposal(_HarnessBaseModel):
    proposal_type: str
    source_entry_id: Optional[str] = None
    proposed_entry: CatalogEntry
    evidence: JudgeResult
    confidence: float = 0.0


class ObjectiveTask(_HarnessBaseModel):
    goal_id: str
    goal_type: str
    elicitation_turns: list[str]
    description: str = ""


class ObjectiveTrace(_HarnessBaseModel):
    goal_id: str
    session_id: str
    responses: list[str] = Field(default_factory=list)
    inferred_disclosure_level: str = "none"


class ObjectiveScript(_HarnessBaseModel):
    goal_id: str
    imperative: str
    context_hint: str = ""
    distilled_from: list[str] = Field(default_factory=list)
