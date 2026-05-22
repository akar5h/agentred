# jakk — black-box MCP scanner

`jakk` connects to an MCP endpoint, enumerates its tools, and fires a
curated library of single-call adversarial probes against tools it
judges compatible. Each probe carries a matcher that decides whether
the response (or the schema) indicates a vulnerability. The goal is a
low-noise, high-signal scan that takes seconds and ships findings to
console + JSONL.

`jakk` is the black-box sibling of `grafted`. Where grafted runs
multi-turn adaptive LLM attacks, jakk fires one-shot, deterministic
MCP probes — no attacker LLM, no oracle, no memory. Different layer
of the stack.

**Status:** v0.2 (May 2026). 11 probes across 6 surfaces: tool_call,
tool_list, resource_list, prompt_list, auth, authz. Verified across 6
live targets (breach-to-fix ch01 / ch02 / ch08, vulnerable + secure
variants).

## Probe catalog

| Probe | Class | Severity | Side-effect |
|---|---|---|---|
| `mcp.command.shell_marker` | command injection (sink) | high | unsafe |
| `mcp.command.secret_file_read` | command injection (impact) | critical | unsafe |
| `mcp.path.prefix_bypass` | CVE-2025-53110 startswith bypass | high | unsafe |
| `mcp.path.canary_file_read` | path traversal (impact) | critical | unsafe |
| `mcp.response.secret_overshare` | secret leak in benign response | high | safe |
| `mcp.response.directive_passthrough` | indirect injection via response | high | safe |
| `mcp.schema.description_smuggling` | tool poisoning via description | high | safe |
| `mcp.auth.no_credential` | anonymous access accepted | critical | safe |
| `mcp.auth.invalid_token` | garbage token accepted | critical | safe |
| `mcp.auth.wrong_prefix` | bearer accepted without scheme | high | safe |
| `mcp.authz.cross_tenant_read` | confused deputy / BOLA | critical | safe |

Full per-probe docs: `docs/jakk/README.md`. Threat-model reference:
`docs/jakk/threat-models.md`.

## Quick start

```bash
pip install -e jakk[dev]

# Bring up a vulnerable target (breach-to-fix ch08)
docker compose -f examples/external_targets/_vendor/mcp-breach-to-fix-labs/docker-compose.yml \
  up -d git-command-injection-vulnerable git-command-injection-secure

# Full library against a vulnerable endpoint — expect findings
jakk mcp scan \
  --endpoint http://127.0.0.1:8008/mcp/stream \
  --library jakk/library/mcp

# Secure endpoint — expect zero command-injection / path-traversal findings
jakk mcp scan \
  --endpoint http://127.0.0.1:9008/mcp/stream \
  --library jakk/library/mcp
```

### Running against an authenticated server

```bash
# Bearer auth
jakk mcp scan \
  --endpoint https://api.example.com/mcp/stream \
  --library jakk/library/mcp \
  --bearer "$ACCESS_TOKEN"

# OAuth token from a file (CI secrets)
jakk mcp scan \
  --endpoint https://api.example.com/mcp/stream \
  --library jakk/library/mcp \
  --oauth-token-file /run/secrets/oauth.txt

# Custom headers
jakk mcp scan \
  --endpoint https://api.example.com/mcp/stream \
  --library jakk/library/mcp \
  --header "X-Workspace-Id=ws_123" \
  --header "X-Trace=jakk-scan"
```

### Safe-only mode (production / commercial servers)

```bash
# Only run probes annotated side_effect: safe.
# Excludes command-injection and path-traversal probes that mutate state.
jakk mcp scan \
  --endpoint https://api.example.com/mcp/stream \
  --library jakk/library/mcp \
  --safe \
  --bearer "$ACCESS_TOKEN"
```

### Cross-tenant authz probe (two credentials)

```bash
# Two identities + a foreign object ID.
# Probe attempts to read A's object using B's credential and watches for the leak.
jakk mcp scan \
  --endpoint http://127.0.0.1:8001/mcp/stream \
  --library jakk/library/mcp \
  --select mcp.authz.cross_tenant_read \
  --cred-a alpha-api-key \
  --cred-b bravo-api-key \
  --foreign-id CRM-1001
```

### Other useful flags

```bash
# Single probe
jakk mcp scan --endpoint <URL> --library <DIR> --select mcp.command.shell_marker

# Filter by OWASP code
jakk mcp scan --endpoint <URL> --library <DIR> --owasp MCP05

# Emit JSONL for downstream tooling
jakk mcp scan --endpoint <URL> --library <DIR> --jsonl /tmp/jakk-results.jsonl

# CI mode: exit nonzero when any finding fires
jakk mcp scan --endpoint <URL> --library <DIR> --exit-nonzero-on-fired
```

## Outcomes

Each probe produces a finding with one of these outcomes:

| Outcome | Meaning |
|---|---|
| `vulnerable` | Evidence in the response that the server's behavior diverges from the security property it should hold. |
| `echo` | Marker reflected back alongside payload syntax — server reflects input but doesn't interpret it. Not exploitable on its own. |
| `suggestive` | Corroboration disagreed across calls (real_1 fired, real_2 didn't, or similar). Rerun to disambiguate. |
| `pass` | Probe ran, response was clean. |
| `skipped` | Probe didn't run — no compatible tool, or missing required config (e.g. `--bearer` for `wrong_prefix`). |
| `error` | Probe ran but the server returned an error and no signal matched. Usually a probe-design mismatch. |

`vulnerable` is the only outcome that warrants triage. See
`docs/jakk/threat-models.md` for what each class of vulnerability
actually allows an attacker to do.

## See also

- `docs/jakk/README.md` — full catalog and YAML schema
- `docs/jakk/threat-models.md` — per-class threat models and attacker model
- `docs/jakk/2026-05-22_smoke-report.md` — live results on the breach-to-fix labs
- `docs/jakk/2026-05-22_discovery.md` + `docs/jakk/2026-05-22_v0.2_discovery.md` — design + lessons
