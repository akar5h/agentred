from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ORACLE_MAP = {
    "LEAK_SCHEMA": "schema_leak",
    "LEAK_PROMPT": "prompt_leak",
    "LEAK_STATE": "state_leak",
    "LEAK_BEHAVIORAL": "behavioral_leak",
    "PERSISTENCE": "persistence",
    "CANARY_EXFILTRATED": "canary_exfiltrated",
    "UNAUTHORIZED_WRITE": "unauthorized_write",
    "WRITE_INTERNAL": "write_internal",
    "POLICY_OVERRIDE": "policy_override",
    "TOOL_EXFIL": "tool_exfil_attempt",
    "tool_exfil": "tool_exfil_attempt",
    "SIDE_CHANNEL_URL": "side_channel_url",
    "HIGH_VALUE_EXFIL": "high_value_exfil",
    "CROSS_SESSION_LEAK": "cross_session_leak",
    "MEMORY_WRITE_POISONING": "memory_write_poisoning",
    "DATA_POISONING": "data_poisoning",
    "MARKER_WRITE": "marker_write",
    "CROSS_BOUNDARY_EXFIL": "cross_boundary_exfil",
    "API_SURFACE_EXFIL": "api_surface_exfil",
    "OUT_OF_SCOPE_READ": "out_of_scope_read",
    # passthrough (already lowercase)
    "schema_leak": "schema_leak",
    "prompt_leak": "prompt_leak",
    "state_leak": "state_leak",
    "behavioral_leak": "behavioral_leak",
    "tool_exfil_attempt": "tool_exfil_attempt",
}


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Convert deepagent fixture JSON to harness catalog JSON")
    p.add_argument("--input", required=True, help="Input fixture JSON path")
    p.add_argument("--output", required=True, help="Output catalog JSON path")
    p.add_argument("--suite-id", default="", help="Optional suite_id override")
    return p.parse_args()


def _map_oracle_codes(raw_codes: list) -> list[str]:
    out: list[str] = []
    for raw in raw_codes:
        key = str(raw)
        mapped = ORACLE_MAP.get(key)
        if mapped:
            out.append(mapped)
        else:
            print(f"[convert_fixture] warning: unknown oracle code '{key}' (skipped)", file=sys.stderr)
    return out


def _convert_attack(attack: dict) -> dict:
    return {
        "id": str(attack.get("id", "")),
        "category": str(attack.get("category", "")),
        "severity": str(attack.get("severity", "")),
        "technique_family": str(attack.get("technique_family", "")),
        "objective": str(attack.get("objective", "")),
        "success_criteria": str(attack.get("success_criteria", "")),
        "oracle_codes": _map_oracle_codes(list(attack.get("oracle_codes", []))),
        "owasp": [str(x) for x in attack.get("owasp", [])],
        "atlas": [str(x) for x in attack.get("atlas", [])],
        "prelude_turns": [str(x) for x in attack.get("prelude_turns", [])],
        "turns": [str(x) for x in attack.get("turns", [])],
    }


def main() -> int:
    args = _parse_args()
    in_path = Path(args.input)
    out_path = Path(args.output)

    if not in_path.exists():
        print(f"[convert_fixture] error: input file not found: {in_path}", file=sys.stderr)
        return 1

    try:
        payload = json.loads(in_path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"[convert_fixture] error: invalid JSON: {exc}", file=sys.stderr)
        return 1

    if not isinstance(payload, dict) or not isinstance(payload.get("attacks"), list):
        print("[convert_fixture] error: input must contain an attacks array", file=sys.stderr)
        return 1

    converted_attacks = [_convert_attack(a) for a in payload.get("attacks", []) if isinstance(a, dict)]
    suite_id = args.suite_id.strip() or str(payload.get("suite_id", "")).strip() or in_path.stem

    out_payload = {
        "suite_id": suite_id,
        "version": "1.0",
        "attack_surface": "direct_chat",
        "attacks": converted_attacks,
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out_payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"[convert_fixture] wrote {out_path} ({len(converted_attacks)} attacks)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
