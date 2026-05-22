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

## Tests in v0.2

| id | OWASP | severity | side_effect | expected_signal | doc |
|---|---|---|---|---|---|
| `mcp.command.shell_marker` | MCP05 | high | unsafe | `input.command_injection` | [tests/mcp.command.shell_marker.md](tests/mcp.command.shell_marker.md) |
| `mcp.command.secret_file_read` | MCP05 | critical | unsafe | `input.command_injection` | [tests/mcp.command.secret_file_read.md](tests/mcp.command.secret_file_read.md) |
| `mcp.path.prefix_bypass` | MCP04 | high | unsafe | `input.path_traversal` | [tests/mcp.path.prefix_bypass.md](tests/mcp.path.prefix_bypass.md) |
| `mcp.path.canary_file_read` | MCP04/02 | critical | unsafe | `input.path_traversal` | [tests/mcp.path.canary_file_read.md](tests/mcp.path.canary_file_read.md) |
| `mcp.response.secret_overshare` | MCP02/05 | high | safe | `response.secret_leak` | [tests/mcp.response.secret_overshare.md](tests/mcp.response.secret_overshare.md) |
| `mcp.response.directive_passthrough` | MCP03 | high | safe | `response.directive_passthrough` | [tests/mcp.response.directive_passthrough.md](tests/mcp.response.directive_passthrough.md) |
| `mcp.schema.description_smuggling` | MCP01/03 | high | safe | `schema.tool_poisoning` | [tests/mcp.schema.description_smuggling.md](tests/mcp.schema.description_smuggling.md) |
| `mcp.auth.no_credential` | MCP10 | critical | safe | `auth.anonymous_access` | [tests/mcp.auth.no_credential.md](tests/mcp.auth.no_credential.md) |
| `mcp.auth.invalid_token` | MCP10 | critical | safe | `auth.token_not_validated` | [tests/mcp.auth.invalid_token.md](tests/mcp.auth.invalid_token.md) |
| `mcp.auth.wrong_prefix` | MCP10 | high | safe | `auth.scheme_not_enforced` | [tests/mcp.auth.wrong_prefix.md](tests/mcp.auth.wrong_prefix.md) |

`--safe` runs only the rows with `side_effect: safe` — the 3 auth probes + the 3 response/schema probes (6 total). Use it against any server where state mutation is unacceptable (production, commercial, anything you don't own).

## Library YAML schema

```yaml
id: <dotted slug>                # required, unique across library
surface: tool_call | tool_list | resource_list | prompt_list | auth
description: |
  Free-form prose.
owasp: [MCP01, MCP05, ...]       # optional, used by --owasp filter
atlas: [AML.T0051, ...]          # optional
severity: info | low | medium | high | critical
side_effect: safe | unsafe       # default unsafe; --safe filters to safe only
expected_signal: <stable class>  # emitted on the finding

applies_to:                          # which discovered tools to fire against
  tool_name: <exact name>            # optional
  tool_name_regex: <pyregex>         # optional, re.search semantics
  min_string_args: <int>             # optional
  require_no_required_args: false    # true → skip tools whose inputSchema.required is non-empty
  none: false                        # true → skip tool selection (schema-only)

payload:
  tool: <name>                   # optional override; defaults to matched tool
  arguments:
    <key>: <value>               # strings may use {run_id}
    __first_string_arg__: <val>  # special: assign to tool's first string arg

# Required when surface == "tool_call" | "tool_list" | "resource_list" | "prompt_list":
matcher:
  kind: substring | regex | marker_echo | secret_pattern
      | directive_passthrough | schema_field
  params:                        # kind-specific; see jakk/jakk/matchers.py
    ...

# Required when surface == "auth":
auth_override:
  mode: none | garbage | wrong_prefix
  expect_success: vulnerable | pass   # default vulnerable
```

Matchers receive a `{run_id}`-templated copy of `params`. `marker_template`
is conventionally promoted into `marker` after template expansion.

## CLI flags added in v0.2

| Flag | Purpose |
|---|---|
| `--safe` | Filter to `side_effect: safe` probes only. |
| `--bearer TOKEN` | Send `Authorization: Bearer <token>` on every request. |
| `--oauth-token-file PATH` | Read bearer from file (CI secrets). Mutually exclusive with `--bearer`. |
| `--header KEY=VALUE` | Custom HTTP header. Pass multiple times. |
