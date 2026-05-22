# `mcp.auth.no_credential`

**OWASP:** MCP10 (auth & access) · **severity:** critical · **signal:** `auth.anonymous_access`
**side_effect:** safe — one `tools/list` call, no tool invocation

## What it is
Opens a streamable-HTTP MCP connection with **no `Authorization` header**.
If the server returns a tool list, anonymous callers can enumerate the
tool surface — and from there, frequently call tools too. This is the
canonical "auth proxy not wired up" misconfiguration.

## Why we picked it
Lowest-cost finding possible: one network round trip, no payload, no
heuristic. Should run unconditionally against every server jakk
encounters that *should* be authenticated. If a server is public by
design (documentation server, capability discovery endpoint), the
operator can flip `auth_override.expect_success: pass` in a local
override of the YAML, or skip via `--owasp` / `--select`.

## How it fires
1. Construct a `StreamableHttpTransport` with `auth=None` and an empty
   header set (no `Authorization`).
2. Open `fastmcp.Client` against it.
3. Call `list_tools()`.
4. **Success** → `vulnerable` (anonymous access permitted). Evidence
   includes the count of tools returned.
   **Exception** → `pass` (server rejected the handshake — expected).

## How detection works
Connection success/failure is the entire verdict; no matcher runs.
Exceptions from fastmcp are caught and translated to `pass`. Any
unexpected exception type still results in `pass` (we don't claim a
finding on transport-layer failures we can't classify).

## Expected results
- Server with a working auth gateway → `pass`.
- Server with no auth, or auth gateway misconfigured → `vulnerable`.
- breach-to-fix lab containers (no auth by design) → `vulnerable` (correct — the labs are intentionally open).

## YAML shape
See `jakk/library/mcp/mcp.auth.no_credential.yaml`.
