from __future__ import annotations

from enum import Enum


class Status(str, Enum):
    SUCCESS = "Success"
    INJECTION = "Injection"
    PARTIAL = "Partial"
    BLOCKED = "Blocked"
    INFRA_FAIL = "InfraFail"


class OracleCode(str, Enum):
    # Leak oracles
    PROMPT_LEAK = "prompt_leak"
    STATE_LEAK = "state_leak"
    SCHEMA_LEAK = "schema_leak"
    BEHAVIORAL_LEAK = "behavioral_leak"
    CANARY_EXFILTRATED = "canary_exfiltrated"
    PERSISTENCE = "persistence"
    CROSS_SESSION_LEAK = "cross_session_leak"
    # Write oracles
    UNAUTHORIZED_WRITE = "unauthorized_write"
    WRITE_INTERNAL = "write_internal"
    PII_WRITE = "pii_write"
    TOOL_HIJACK_WRITE = "tool_hijack_write"
    MARKER_WRITE = "marker_write"
    OVERWRITE_POISONING = "overwrite_poisoning"
    # Semantic oracles
    POLICY_OVERRIDE = "policy_override"
    DATA_POISONING = "data_poisoning"
    DELAYED_ACTIVATION = "delayed_activation"
    MEMORY_WRITE_POISONING = "memory_write_poisoning"
    # Exfil policy oracles
    TOOL_EXFIL_ATTEMPT = "tool_exfil_attempt"
    SIDE_CHANNEL_URL = "side_channel_url"
    OUT_OF_SCOPE_READ = "out_of_scope_read"
    HIGH_VALUE_EXFIL = "high_value_exfil"
    CROSS_BOUNDARY_EXFIL = "cross_boundary_exfil"
    SINK_CONFIRMED = "sink_confirmed"
    API_SURFACE_EXFIL = "api_surface_exfil"
    # Soft DoS
    LOOP_DRIFT = "loop_drift"


class FailureReason(str, Enum):
    NOT_SURFACED = "NOT_SURFACED"
    TRUNCATED = "TRUNCATED"
    IGNORED = "IGNORED"
    DEFENSE_TRIGGERED = "DEFENSE_TRIGGERED"
    TOOL_REFUSED = "TOOL_REFUSED"
    ENV_CONSTRAINT = "ENV_CONSTRAINT"


class VesselKind(str, Enum):
    DIRECT_PROMPT = "direct_prompt"
    UPLOADED_DOCUMENT = "uploaded_document"
    TOOL_OUTPUT = "tool_output"
    MEMORY_ENTRY = "memory_entry"
    SUBAGENT_OUTPUT = "subagent_output"
    TOOL_SCHEMA = "tool_schema"


class AttackSurface(str, Enum):
    DIRECT_CHAT = "direct_chat"
    INDIRECT_UPLOAD = "indirect_upload"
    MEMORY_POISONING = "memory_poisoning"
    TOOL_POISONING = "tool_poisoning"
    DATA_EXTRACTION = "data_extraction"
    SUBAGENT_INJECTION = "subagent_injection"
    EXTERNAL_API_EXPLOITATION = "external_api_exploitation"
    TOOL_SCHEMA_ENUMERATION = "tool_schema_enumeration"
