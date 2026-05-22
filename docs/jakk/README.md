---
date: 2026-05-22
status: jakk v0.1 catalog
scope: MCP black-box single-call probes
---

# jakk — MCP scanner catalog

`jakk` ships a small, curated library of single-call probes. Each test
targets one OWASP-for-MCP class, fires deterministically (no LLM in the
loop), and includes a matcher that decides whether the probe fired based
on the response or the tool schema alone.

## How jakk differs from grafted

| | grafted | jakk |
|---|---|---|
| Attacker | LLM-driven, adaptive | deterministic payload table |
| Turns per probe | multi-turn, memory-carrying | single-shot |
| Target surface | full agent (HTTP/MCP/AgentDojo) | MCP endpoint only |
| Detection | oracle LLM + heuristics | regex / substring / canary echo |
| Latency | seconds–minutes per attack | <1s per probe |
| Cost | LLM tokens per turn | zero LLM cost |

jakk's job is the easy half: catch the bugs you can catch without an LLM
in the loop, fast and reliably. grafted's job is the hard half: bugs
that only show up under adaptive pressure.

## Quick run

```bash
jakk mcp scan --endpoint http://127.0.0.1:8008/mcp/stream --library jakk/library/mcp
jakk mcp scan --endpoint http://127.0.0.1:8008/mcp/stream --library jakk/library/mcp --select mcp.command.shell_marker
jakk mcp scan --endpoint http://127.0.0.1:8008/mcp/stream --library jakk/library/mcp --owasp MCP05 --jsonl /tmp/jakk-results.jsonl
```

## Tests in v0.1

| id | OWASP | severity | expected_signal | doc |
|---|---|---|---|---|
| `mcp.command.shell_marker` | MCP05 | high | `input.command_injection` | [tests/mcp.command.shell_marker.md](tests/mcp.command.shell_marker.md) |
| `mcp.command.secret_file_read` | MCP05 | critical | `input.command_injection` | [tests/mcp.command.secret_file_read.md](tests/mcp.command.secret_file_read.md) |
| `mcp.path.prefix_bypass` | MCP04 | high | `input.path_traversal` | [tests/mcp.path.prefix_bypass.md](tests/mcp.path.prefix_bypass.md) |
| `mcp.path.canary_file_read` | MCP04/02 | critical | `input.path_traversal` | [tests/mcp.path.canary_file_read.md](tests/mcp.path.canary_file_read.md) |
| `mcp.response.secret_overshare` | MCP02/05 | high | `response.secret_leak` | [tests/mcp.response.secret_overshare.md](tests/mcp.response.secret_overshare.md) |
| `mcp.response.directive_passthrough` | MCP03 | high | `response.directive_passthrough` | [tests/mcp.response.directive_passthrough.md](tests/mcp.response.directive_passthrough.md) |
| `mcp.schema.description_smuggling` | MCP01/03 | high | `schema.tool_poisoning` | [tests/mcp.schema.description_smuggling.md](tests/mcp.schema.description_smuggling.md) |

## Library YAML schema

```yaml
id: <dotted slug>                # required, unique across library
surface: tool_call | tool_list | resource_list | prompt_list
description: |
  Free-form prose.
owasp: [MCP01, MCP05, ...]       # optional, used by --owasp filter
atlas: [AML.T0051, ...]          # optional
severity: info | low | medium | high | critical
expected_signal: <stable class>  # emitted on the finding

applies_to:                      # which discovered tools to fire against
  tool_name: <exact name>        # optional
  tool_name_regex: <pyregex>     # optional, re.search semantics
  min_string_args: <int>         # optional
  none: false                    # true → skip tool selection (schema-only)

payload:
  tool: <name>                   # optional override; defaults to matched tool
  arguments:
    <key>: <value>               # strings may use {run_id}
    __first_string_arg__: <val>  # special: assign to tool's first string arg

matcher:
  kind: substring | regex | marker_echo | secret_pattern
      | directive_passthrough | schema_field
  params:                        # kind-specific; see jakk/jakk/matchers.py
    ...
```

Matchers receive a `{run_id}`-templated copy of `params`. `marker_template`
is conventionally promoted into `marker` after template expansion.
