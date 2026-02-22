# TRD-01: Phase 0 — Foundation

**Acceptance Gate:** `pytest tests/unit/test_schemas.py` passes (0 errors, all asserts green)

---

## Scope

Phase 0 establishes the typed skeleton. No HTTP calls, no attack logic, no oracle computation. Every later phase imports from `harness/core/`.

**Files to create:**

```
harness/__init__.py
harness/core/__init__.py
harness/core/enums.py
harness/core/schemas.py
harness/core/exceptions.py
harness/victim/__init__.py
harness/victim/base.py
harness/attack/__init__.py
harness/attack/base.py
harness/oracle/__init__.py
harness/oracle/base.py
tests/__init__.py
tests/unit/__init__.py
tests/integration/__init__.py
tests/conftest.py
tests/unit/test_schemas.py
```

---

## `harness/core/enums.py`

All enums are `str` subclasses so they serialize cleanly to JSON.

```python
from enum import Enum

class Status(str, Enum):
    SUCCESS     = "Success"
    INJECTION   = "Injection"
    PARTIAL     = "Partial"
    BLOCKED     = "Blocked"
    INFRA_FAIL  = "InfraFail"

class OracleCode(str, Enum):
    # Leak oracles
    PROMPT_LEAK       = "prompt_leak"
    STATE_LEAK        = "state_leak"
    SCHEMA_LEAK       = "schema_leak"
    BEHAVIORAL_LEAK   = "behavioral_leak"
    CANARY_EXFILTRATED= "canary_exfiltrated"
    PERSISTENCE       = "persistence"
    CROSS_SESSION_LEAK= "cross_session_leak"
    # Write oracles
    UNAUTHORIZED_WRITE= "unauthorized_write"
    WRITE_INTERNAL    = "write_internal"
    PII_WRITE         = "pii_write"
    TOOL_HIJACK_WRITE = "tool_hijack_write"
    MARKER_WRITE      = "marker_write"
    OVERWRITE_POISONING = "overwrite_poisoning"
    # Semantic oracles
    POLICY_OVERRIDE   = "policy_override"
    DATA_POISONING    = "data_poisoning"
    DELAYED_ACTIVATION= "delayed_activation"
    MEMORY_WRITE_POISONING = "memory_write_poisoning"
    # Exfil policy oracles
    TOOL_EXFIL_ATTEMPT= "tool_exfil_attempt"
    SIDE_CHANNEL_URL  = "side_channel_url"
    OUT_OF_SCOPE_READ = "out_of_scope_read"
    HIGH_VALUE_EXFIL  = "high_value_exfil"
    CROSS_BOUNDARY_EXFIL = "cross_boundary_exfil"
    SINK_CONFIRMED    = "sink_confirmed"
    API_SURFACE_EXFIL = "api_surface_exfil"
    # Soft DoS
    LOOP_DRIFT        = "loop_drift"

class FailureReason(str, Enum):
    NOT_SURFACED      = "NOT_SURFACED"      # infra fail or empty response
    TRUNCATED         = "TRUNCATED"         # claim but no canary
    IGNORED           = "IGNORED"           # response but no signals
    DEFENSE_TRIGGERED = "DEFENSE_TRIGGERED" # refusal / safety layer
    TOOL_REFUSED      = "TOOL_REFUSED"      # tool call blocked
    ENV_CONSTRAINT    = "ENV_CONSTRAINT"    # injection but no write possible

class VesselKind(str, Enum):
    DIRECT_PROMPT     = "direct_prompt"
    UPLOADED_DOCUMENT = "uploaded_document"
    TOOL_OUTPUT       = "tool_output"
    MEMORY_ENTRY      = "memory_entry"

class AttackSurface(str, Enum):
    DIRECT_CHAT       = "direct_chat"
    INDIRECT_UPLOAD   = "indirect_upload"
    MEMORY_POISONING  = "memory_poisoning"
    TOOL_POISONING    = "tool_poisoning"
    DATA_EXTRACTION   = "data_extraction"
```

---

## `harness/core/schemas.py`

All schemas are `pydantic.BaseModel` with `model_config = ConfigDict(extra="allow")` so unknown catalog fields don't break loading.

### `VesselSpec`

```python
class VesselSpec(BaseModel):
    kind: VesselKind
    delivery_field: str = "message"         # field name for turn injection
    fixture_path: str | None = None         # relative path to fixture file
    render_template: bool = True            # run placeholder substitution?
```

### `TestSpec`

Maps 1:1 to an attack catalog entry.

```python
class TestSpec(BaseModel):
    scenario_id: str                        # e.g. "LB-01"
    suite_id: str                           # e.g. "direct_chat_injection_v1"
    turns: list[str]                        # attack turn templates
    prelude_turns: list[str] = []
    vessels: list[VesselSpec] = []
    oracle_codes: list[OracleCode] = []
    expected: dict = {}                     # v2 expected-driven oracle fields
    adaptive: bool = False
    # Metadata passthrough from catalog
    category: str = ""
    severity: str = ""
    owasp: list[str] = []
    atlas: list[str] = []
    objective: str = ""
    success_criteria: str = ""
    attack_surface: AttackSurface | None = None
    technique_family: str = ""
```

### `JudgeResult`

Returned by `CampaignRunner` after each run.

```python
class JudgeResult(BaseModel):
    run_id: str
    scenario_id: str
    suite_id: str
    rep: int = 1
    status: Status
    failure_reason: FailureReason | None = None
    suggested_variant: str = ""
    reflection_notes: list[str] = []
    attack_surface: AttackSurface | None = None
    technique_family: str = ""
    hard_flags: dict[str, bool] = {}
    soft_success: bool = False
    soft_score: float = 0.0
    soft_findings: list[dict] = []
    write_delta: int = 0
    canary_token: str = ""
    session_id: str = ""
    turn_count: int = 0
    final_response: str = ""
    duration_ms: int = 0
    error: str = ""
    notes: list[str] = []
```

### `TelemetryEvent`

```python
class TelemetryEvent(BaseModel):
    run_id: str
    scenario_id: str
    suite_id: str
    event_type: str                         # see harness/telemetry/events.py
    turn_index: int = -1
    content: str = ""
    canary_token: str = ""
    meta: dict = {}
    timestamp_iso: str = ""
```

### `TargetProfile`

Loaded from `HARNESS_TARGET_PROFILE_PATH` JSON. Enables provenance-gated oracles.

```python
class TargetProfile(BaseModel):
    known_internal_tool_names: list[str] = []
    known_internal_state_keys: list[str] = ["thread_id", "checkpoint", "configurable"]
```

### `RunConfig`

Top-level configuration for a campaign run.

```python
class RunConfig(BaseModel):
    catalog_path: str
    base_url: str = "http://localhost:8000"
    target_mode: str = "chat"               # chat | stream
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
    scenario_filter: list[str] = []
    run_dir: str = ""
    max_cost_usd: float = 10.0
    target_profile_path: str = ""
```

---

## `harness/core/exceptions.py`

```python
class HarnessError(Exception):
    """Base class for all harness errors."""

class InfraError(HarnessError):
    """HTTP/network failure communicating with the victim."""

class CatalogError(HarnessError):
    """Catalog load or validation failure."""

class OracleError(HarnessError):
    """Oracle evaluation failure (e.g. LLM oracle API error)."""

class VictimResetError(HarnessError):
    """Failed to reset victim session between runs."""
```

---

## `harness/victim/base.py`

```python
from abc import ABC, abstractmethod

class VictimAdapter(ABC):
    """Abstract base class for all victim integrations."""

    @abstractmethod
    async def send_turn(
        self,
        session_id: str,
        message: str,
        *,
        mode: str = "chat",
        timeout: float = 120.0,
    ) -> dict:
        """
        Send one conversation turn and return a dict with keys:
          - response: str
          - usage: dict (tokens, model_id, etc.)
          - duration_ms: int
        Raises InfraError on HTTP/network failure.
        """

    @abstractmethod
    async def upload_file(
        self,
        session_id: str,
        filename: str,
        content: bytes,
        content_type: str,
        *,
        timeout: float = 120.0,
    ) -> dict:
        """
        Upload a file to the victim. Returns the server response dict.
        Raises InfraError on failure.
        """

    @abstractmethod
    async def list_docs(
        self,
        session_id: str,
        *,
        timeout: float = 30.0,
    ) -> list[dict]:
        """
        List documents visible to the given session.
        Returns list of doc dicts (must include "id" key).
        Raises InfraError on failure.
        """

    @abstractmethod
    async def reset_session(
        self,
        session_id: str,
        *,
        timeout: float = 10.0,
    ) -> None:
        """
        Reset/clear the session state on the victim.
        Raises VictimResetError if reset fails.
        """
```

---

## `harness/attack/base.py`

```python
from abc import ABC, abstractmethod

class AttackStrategy(ABC):
    """Abstract base class for attack turn synthesis."""

    @abstractmethod
    async def next_turn(
        self,
        *,
        scenario_id: str,
        objective: str,
        base_turn: str,
        transcript: list[dict],
    ) -> str:
        """
        Given the base attack turn and the current transcript,
        return the turn to actually send to the victim.

        StaticStrategy returns base_turn unchanged.
        LlmSynthStrategy uses PyRIT to mutate the turn adaptively.
        """

    @property
    @abstractmethod
    def is_adaptive(self) -> bool:
        """Return True if this strategy modifies turn text."""
```

---

## `harness/oracle/base.py`

```python
from abc import ABC, abstractmethod
from harness.core.schemas import JudgeResult

class Oracle(ABC):
    """Abstract base class for all oracles."""

    @abstractmethod
    async def evaluate(self, observation: dict) -> JudgeResult:
        """
        Evaluate an observation dict and return a JudgeResult.

        The observation dict follows the scoring.py contract:
          - ok: bool
          - error: str
          - response_concat: str
          - write_delta: int
          - canary_token: str
          - suite_id: str
          - expected: dict
          - new_docs_sample: list[dict]
          - transcript: list[dict]
          - responses: list[str]
          - max_identical_assistant_turns: int
          - ... (other fields from campaign runner)
        """
```

---

## `tests/conftest.py`

```python
import pytest

@pytest.fixture
def base_obs():
    """Minimal valid observation dict for oracle tests."""
    return {
        "ok": True,
        "error": "",
        "response_concat": "",
        "write_delta": 0,
        "max_identical_assistant_turns": 0,
        "canary_token": "",
        "suite_id": "",
        "expected": {},
        "new_docs_sample": [],
        "transcript": [],
        "responses": [],
    }

@pytest.fixture
def canary():
    return "CANARY_deadbeef"
```

---

## `tests/unit/test_schemas.py`

Tests that schema instantiation and validation work correctly.

```python
from harness.core.enums import Status, OracleCode, FailureReason, VesselKind, AttackSurface
from harness.core.schemas import (
    VesselSpec, TestSpec, JudgeResult, TelemetryEvent, TargetProfile, RunConfig
)

def test_status_enum_values():
    assert Status.SUCCESS == "Success"
    assert Status.BLOCKED == "Blocked"
    assert Status.INFRA_FAIL == "InfraFail"

def test_oracle_code_enum_roundtrip():
    for code in OracleCode:
        assert OracleCode(code.value) == code

def test_vessel_spec_defaults():
    v = VesselSpec(kind=VesselKind.DIRECT_PROMPT)
    assert v.delivery_field == "message"
    assert v.fixture_path is None
    assert v.render_template is True

def test_test_spec_minimal():
    t = TestSpec(scenario_id="LB-01", suite_id="direct_chat_injection_v1", turns=["Hello"])
    assert t.adaptive is False
    assert t.prelude_turns == []
    assert t.vessels == []

def test_judge_result_minimal():
    jr = JudgeResult(
        run_id="abc123",
        scenario_id="LB-01",
        suite_id="direct_chat_injection_v1",
        status=Status.BLOCKED,
    )
    assert jr.failure_reason is None
    assert jr.soft_success is False

def test_run_config_defaults():
    rc = RunConfig(catalog_path="some/path.json")
    assert rc.target_mode == "chat"
    assert rc.runs_per_scenario == 1

def test_target_profile_defaults():
    tp = TargetProfile()
    assert "thread_id" in tp.known_internal_state_keys

def test_telemetry_event_serializes_to_dict():
    ev = TelemetryEvent(
        run_id="r1",
        scenario_id="LB-01",
        suite_id="direct_chat_injection_v1",
        event_type="turn_sent",
        turn_index=0,
        content="hello",
    )
    d = ev.model_dump()
    assert d["event_type"] == "turn_sent"

def test_failure_reason_values():
    assert FailureReason.NOT_SURFACED == "NOT_SURFACED"
    assert FailureReason.DEFENSE_TRIGGERED == "DEFENSE_TRIGGERED"
```

---

## Dependency Notes

- No external network calls in this phase
- `pydantic>=2.0` required (uses `model_config`, `model_dump()`)
- `harness/core/` must not import from `harness/victim/`, `harness/attack/`, etc.
- `harness/victim/base.py`, `harness/attack/base.py`, `harness/oracle/base.py` may import from `harness/core/` only
