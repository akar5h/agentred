---
date: 2026-05-23
status: creator's technical onboarding for jakk launch
audience: you (the creator) before any public conversation about jakk
scope: every nitty-gritty needed to answer questions confidently
---

# jakk launch-prep — creator's deep onboarding

Read this end-to-end before any podcast / DM / talk / Show HN
comments thread. By the end you should be able to answer any
question about jakk without needing to grep the repo. If a question
in the FAQ stumps you, re-read the relevant section, then re-test
it manually against the lab.

This is technical depth, not pitch material. Tone: honest, precise,
no marketing.

---

## 1 · The one-paragraph version

`jakk` is a black-box scanner for MCP (Model Context Protocol)
servers. You give it an endpoint URL; it enumerates the server's
tools via `tools/list`, fires a curated library of single-call
probes against tools it judges compatible, classifies findings via
deterministic matchers, and writes them to console + JSONL. No
attacker LLM. No oracle. No memory. Findings are classified across
five outcomes: `vulnerable`, `echo`, `pass`, `skipped`, `error`
(plus `suggestive` for corroborated probes with intermittent
signal). Eleven probes ship in v0.2 covering OWASP-for-MCP classes
MCP01-MCP05, MCP08, MCP10.

---

## 2 · Architecture in one diagram

```
                                jakk mcp scan
                                      │
                                      ▼
                    ┌────────────────────────────────┐
                    │ CLI (argparse)                 │
                    │   --endpoint --library         │
                    │   --select --owasp --safe      │
                    │   --bearer --header            │
                    │   --cred-a/-b --foreign-id     │
                    │   --jsonl --timeout            │
                    └────────────────┬───────────────┘
                                     │
                                     ▼
                    ┌────────────────────────────────┐
                    │ library.py (Pydantic models)   │
                    │   TestCase  AppliesTo  Payload │
                    │   Matcher   AuthOverride       │
                    │   AuthzPhase  CorroborateSpec  │
                    │                                │
                    │ load_library(dir) → [TestCase] │
                    │ filter_cases(safe_only, ...)   │
                    └────────────────┬───────────────┘
                                     │
                                     ▼
                    ┌────────────────────────────────┐
                    │ scanner.py (orchestrator)      │
                    └────────────────┬───────────────┘
                                     │
              ┌──────────────────────┼──────────────────────┐
              ▼                      ▼                      ▼
       surface: tool_call     surface: auth          surface: authz
       (also tool_list,             │                      │
        resource_list,        per-probe MCPClient    one MCPClient,
        prompt_list)          with auth_override     phase_a + phase_b
              │                     │                      │
              ▼                     ▼                      ▼
        applies_to filter     list_tools()           plant + read
        per matched tool:     succeeded?             (sanity + probe)
          run matcher,        → vulnerable           matcher on
          or 3-call           raised?                phase_b response
          corroboration       → pass
          (marker_echo)
              │                     │                      │
              └─────────────────────┼──────────────────────┘
                                    ▼
                           ┌────────────────┐
                           │  Finding[]     │
                           │  (5+1 outcomes)│
                           └────────┬───────┘
                                    ▼
                       render_console + JSONL
```

Module map:

| Module | LOC (~) | Responsibility |
|---|---|---|
| `cli.py` | 100 | argparse, flag parsing, header expansion, OAuth-token-file read |
| `library.py` | 200 | Pydantic models, `load_library`, `filter_cases` |
| `applies.py` | 30 | `applies_to` evaluator |
| `matchers.py` | 200 | 6 matcher kinds, registry, `_SHELL_ECHO_TELLS` |
| `mcp_client.py` | 150 | Async wrapper over `fastmcp.Client`; auth resolution |
| `scanner.py` | 350 | `_run_case` / `_run_auth_case` / `_run_authz_case` / `_run_corroborated_marker_echo` |
| `findings.py` | 100 | `Finding`, console rendering, JSONL writer |

Total Python: ~1100 lines. Library YAMLs: 11 files. Per-test docs:
11 files. Tests: 75 unit, no live server required.

---

## 3 · The 5+1-outcome taxonomy

Every probe produces a `Finding` with an `outcome`. Operators read
outcome first; severity second.

| Outcome | Meaning | When you see it | What to do |
|---|---|---|---|
| **vulnerable** | Evidence in the response that the server's behavior diverges from the security property it should hold. | Real bug or matcher false positive — triage. | Read `evidence` + `payload`, reproduce manually, file. |
| **echo** | Marker appears alongside the literal payload syntax. Server reflected raw input but didn't interpret it. | Tools that echo input back without expansion / parsing. | Not actionable on its own. May indicate a separate output-reflection issue. |
| **suggestive** | Corroboration disagreed across calls (e.g. real_1 fired, real_2 didn't). | Only on `marker_echo` probes with `corroborate`. Intermittent behavior — caching / race / network blip. | Rerun. If still suggestive after 2-3, inspect by hand. |
| **pass** | Probe ran, response was clean. | The good case. | Move on. |
| **skipped** | Probe didn't run — no compatible tool, missing CLI flag, `__first_string_arg__` couldn't resolve. | Often. The probe wasn't applicable to this server. | Read `evidence` for the reason. Not a defect. |
| **error** | Probe ran, server returned `isError=True`, no signal matched. | Usually a probe-design mismatch (matched a tool by name but didn't satisfy required args). | TODO for the probe library, not the server. |

**Critical distinction**: `vulnerable` ≠ `fired`. `fired` is the
matcher's boolean. `outcome` is the refined verdict. A matcher can
fire and still classify as `echo` (e.g. marker_echo's shell-tell
detection). Lean on `outcome` in conversations.

---

## 4 · The 11 probes — one paragraph each

### 4.1 `mcp.command.shell_marker` (high, unsafe)
Injects `x$(echo JAKK-MARKER-<id>)` into the first string-typed
arg of any tool matching `(?i)(git|repo|exec|run|init|build|clone|fetch|pull|shell|cmd)`.
If the marker appears in the response *without* the `$(echo …)`
wrapper, shell expansion happened. The matcher's `_SHELL_ECHO_TELLS`
list (`$(`, `${`, `` `echo ``, `; cat`, `&& cat`, `| cat`) detects
the wrapper alongside the marker → classified as `echo`, not
`vulnerable`. v0.2 adds 3-call corroboration: real_1 + real_2 +
negative-canary (`xPLAIN-CANARY-…`); aggregate verdict uses per-call
shell-syntax classification, not raw fired booleans. The naive
aggregation rule (negative didn't fire = vulnerable) failed during
Day 4 smoke because git's `init_bare_repository` creates a directory
named after literal input — the negative reflects too. The fix uses
the existing per-call matcher outcome.

### 4.2 `mcp.command.secret_file_read` (critical, unsafe)
Impact-tier follow-up to `shell_marker`. Same tool match. Payload
uses `;` command chaining (not `$(cat …)` substitution — that trips
the host command's argv parser on multi-line file contents) to call
`cat /app/secrets/deployment_token.txt` and `cat /etc/passwd | head -2`.
Matcher: `secret_pattern` (FLAG{...}, PEM blocks, /etc/passwd root
line, API-key shapes). Fires `vulnerable` when actual file content
(not just our payload) appears in the response.

### 4.3 `mcp.path.prefix_bypass` (high, unsafe)
Targets CVE-2025-53110 shape — `startswith()` allowlist that lets a
sibling directory through. Tool match: `(?i)(list_directory|read_file|directory|file|path|read|list)`
with `min_string_args: 1`. Payload: `/app/files/safe_files_sensitive/`
as first string arg. Matcher: regex on `safe_files_sensitive` or
listing prefix. On ch02 it fires on both `list_directory_contents`
(strong: enumeration succeeded) and `read_file_contents` (weak:
matched on directory name in error message). Sink-tier; impact-tier
sibling is `canary_file_read`.

### 4.4 `mcp.path.canary_file_read` (critical, unsafe)
Impact tier for path traversal. Narrower tool match
(`^(read_file|get_file|cat_file|file_contents|read_file_contents|fetch_file)`)
to avoid firing on list-directory tools. Payload:
`/app/files/safe_files_sensitive/secret.txt` (configurable).
Matcher: `secret_pattern`. On ch02 vulnerable returns
`FLAG{cve_2025_53110_escape_route}`.

### 4.5 `mcp.response.secret_overshare` (high, safe)
Calls any tool matching `^(list|get|read|describe|status|info|inventory|repositories|files|tools)`
with empty args (enforced via `require_no_required_args: true`).
Matcher: `secret_pattern`. Catches servers that leak secrets through
a benign-looking read (e.g. `list_config` returning `API_KEY=...`).
Safe to run against production because the call is genuinely benign.

### 4.6 `mcp.response.directive_passthrough` (high, safe)
Same shape as `secret_overshare` but tool match adds
`news|search|fetch|message|messages|notifications`. Matcher:
`directive_passthrough` regex set targeting `SYSTEM:`,
`Ignore previous instructions`, `You are now…`, `<SYSTEM>`,
`New instructions:`. Catches tool responses that *issue
instructions to the LLM* — the breach-to-fix ch03 pattern. Higher
false-positive risk (a tool returning a blog post about prompt
injection legitimately contains those phrases).

### 4.7 `mcp.schema.description_smuggling` (high, safe)
Zero side-effect, zero tool calls. Inspects `tools/list` for
directive-style language smuggled into tool descriptions or
parameter schema descriptions. The Invariant Labs tool-poisoning
pattern. Surface = `tool_list`, `applies_to.none = true`. The
highest-leverage probe in the library — runs unconditionally
against any server, including production.

### 4.8-4.10 `mcp.auth.no_credential` / `invalid_token` / `wrong_prefix` (critical, critical, high — all safe)
New `surface: auth`. Open a fresh `MCPClient` per probe with
`auth_override`:
- `none` — strip Authorization entirely
- `garbage` — `Bearer garbage-<8-byte-hex>`
- `wrong_prefix` — send the operator's real `--bearer` token without the `Bearer ` scheme prefix

If `list_tools()` succeeds with the override → `vulnerable`. If it
raises → `pass`. `wrong_prefix` skips when `--bearer` isn't
provided.

### 4.11 `mcp.authz.cross_tenant_read` (critical, safe)
`surface: authz`. Two-credential probe with template tokens
`{cred_a}`, `{cred_b}`, `{foreign_id}` threaded into payload
arguments (NOT HTTP headers — many MCPs auth via tool args). Phase
A: identity A reads its own object (sanity check — must succeed,
else `error`). Phase B: identity B attempts the same read. Matcher
applied to phase B's response. On ch01 the matcher regex is
`"tenant"\s*:\s*"tenant_alpha"` — if B's response contains A's
tenant tag, BOLA fired.

---

## 5 · Why these 11 (OWASP-for-MCP coverage)

| OWASP code | Class | Probe(s) |
|---|---|---|
| MCP01 | Prompt injection | `schema.description_smuggling` |
| MCP02 | Excessive output | `response.secret_overshare`, `path.canary_file_read` |
| MCP03 | Indirect prompt injection | `response.directive_passthrough`, `schema.description_smuggling` |
| MCP04 | Insufficient input sanitization | `path.prefix_bypass`, `path.canary_file_read` |
| MCP05 | Insecure tool invocation | `command.shell_marker`, `command.secret_file_read` |
| MCP06 | Excessive agency | — (deferred; LLM-level; grafted's job) |
| MCP07 | Insecure plugins | — (deferred; supply-chain analysis, not black-box) |
| MCP08 | Broken object-level authz | `authz.cross_tenant_read` |
| MCP09 | Insecure default config | — (deferred; vendor-specific) |
| MCP10 | Authentication & access | `auth.no_credential`, `auth.invalid_token`, `auth.wrong_prefix` |

Gaps are honest:
- MCP06 fundamentally about LLM behavior → grafted territory.
- MCP07 needs static analysis of server dependencies.
- MCP09 needs per-vendor knowledge to generically detect.

---

## 6 · The honest gaps (what jakk does NOT do)

Memorize these. The press will ask.

1. **Single-call only.** No multi-turn, no adaptive escalation, no memory. By design — grafted's job.
2. **No LLM in the loop.** Regex/substring/pattern matchers. Can't catch bugs that need semantic understanding.
3. **Black-box only.** No source-code analysis. No dependency tree. No build artifacts.
4. **Tool-name-regex selection.** A path-traversal tool named `fetch_remote` won't match `prefix_bypass`'s regex. Conservative; misses some legitimate matches.
5. **English-only matchers.** Directive patterns are English. Other languages are invisible.
6. **No write-side probes by default.** Day 5+ work; documented in `depth-of-exposure-methodology.md`.
7. **Multi-required-arg tools may produce `error`.** `shell_marker` fills only the first string arg. ch01's `fetch_project(project_id, api_key)` errors because `api_key` is unfilled. v0.3 fix.
8. **No fuzzing.** Hand-authored payloads only. Different tool category.
9. **No rate-limit awareness.** Operators self-rate-limit for commercial targets.
10. **No credentials discovery / harvesting.** Operator supplies `--bearer` / `--cred-a` / `--cred-b`.

---

## 7 · YAML schema cheat sheet

```yaml
id: <dotted slug>            # required, unique
surface: tool_call | tool_list | resource_list | prompt_list | auth | authz
description: |
  free-form prose
owasp: [MCP05, ...]          # optional, used by --owasp filter
atlas: [AML.T0051, ...]      # optional
severity: info | low | medium | high | critical
side_effect: safe | unsafe   # default unsafe; --safe filters to safe only
expected_signal: <stable class>

applies_to:                  # ignored for surface=auth
  tool_name: <exact>             # OR
  tool_name_regex: <pyregex>     # AND
  min_string_args: <int>         # AND
  require_no_required_args: bool # AND
  none: bool                     # short-circuit

payload:                     # ignored for surface=auth/authz
  tool: <name>                   # optional
  arguments:
    <key>: <value>               # strings may use {run_id}
    __first_string_arg__: <val>  # → tool's first string arg

matcher:                     # required for tool_call/tool_list/authz
  kind: substring | regex | marker_echo | secret_pattern
      | directive_passthrough | schema_field
  params: ...

auth_override:               # required for surface=auth
  mode: none | garbage | wrong_prefix
  expect_success: vulnerable | pass

phase_a: { tool, arguments }  # required for surface=authz
phase_b: { tool, arguments }

corroborate:                 # optional, effective with marker_echo
  negative_arguments: ...
  negative_marker_template: <str>
```

---

## 8 · The 30-question FAQ

### Concept & scope

**Q1. What is jakk in one sentence?**
A black-box scanner for MCP (Model Context Protocol) servers that
fires deterministic single-call probes and classifies findings via
matchers — no LLM in the loop.

**Q2. Why does this need to exist?**
The only MCP-aware tools today are (a) vendor-side testing
utilities, (b) labs that demonstrate bugs without scanning, (c)
general-purpose web scanners that don't understand MCP. A
purpose-built black-box scanner shrinks "I'm running an MCP
server" → "I know it has these bugs" from hours to seconds.

**Q3. Why not Burp / nuclei / OWASP ZAP?**
Those work at the HTTP layer. No model of `tools/list`,
`tools/call`, session-id, or the MCP attacker model (where the
attacker is content the LLM ingests, not the scan operator).
MCP-aware probes like `schema.description_smuggling` can't be
expressed in a generic HTTP scanner.

**Q4. How is this different from grafted?**
Different layer. grafted runs multi-turn LLM-driven adaptive
attacks against an agent (MCP consumer). jakk fires single-call
deterministic probes against the MCP server (infrastructure).
They compose: jakk findings can seed grafted's strategic memory.

**Q5. Is this just MCP attacking MCP?**
No. jakk runs as a CLI. It is *not* itself an MCP server. We
considered and rejected MCP-server distribution for v1 — see
`mcp-server-distribution-decision.md`. The interesting target for
"MCP attacking" is the LLM agent consuming MCP, which is grafted's
job.

**Q6. What's MCP itself?**
Anthropic's Model Context Protocol. JSON-RPC 2.0 over stdio /
streamable-HTTP / SSE. Lets LLM clients discover and call tools
from external servers uniformly. ~70% of MCP servers in the wild
use FastMCP (Python server SDK).

### How it works

**Q7. How does a scan work, step by step?**
1. Open `fastmcp.Client` against endpoint with configured auth.
2. Call `tools/list`. 3. Load YAML library. 4. For each probe:
filter by `--select`/`--owasp`/`--safe`; apply `applies_to`; expand
`{run_id}` / `__first_string_arg__`; call `tools/call`; run
matcher; produce Finding. 5. Render console; write JSONL.

**Q8. What's `applies_to`?**
Filter for which discovered tools a probe fires against. Five
mutually-AND fields: `tool_name`, `tool_name_regex`,
`min_string_args`, `require_no_required_args`, `none`. Conservative
by default.

**Q9. What's `__first_string_arg__`?**
Reserved key in `payload.arguments`. Tells the scanner: assign
this value to whatever the first string-typed parameter of the
matched tool is. Lets one probe target tools with different
parameter names.

**Q10. What's the corroboration logic?**
For `marker_echo` probes with `corroborate`, the scanner runs 3
calls per matched tool: real_1, real_2 (fresh run_id), negative
(no-metacharacter control). Aggregate verdict uses per-call
matcher outcomes. Both reals == vulnerable → outcome vulnerable
(negative is informational). Both reals == echo → outcome echo.
Reals disagree → suggestive.

**Q11. Why use per-call outcome instead of raw fired booleans?**
First version aggregated on raw fired + negative tie-breaker.
Failed on ch08 (git): negative payload is a valid directory name,
so it reflects too; aggregation said echo. But ch08 IS vulnerable.
Per-call matcher already understood the distinction via the
shell-syntax check; using its outcome avoids re-deriving the
analysis at aggregation time.

### Outcomes

**Q12. What's the difference between vulnerable and echo?**
`vulnerable` = response evidence the server diverged from its
intended security property (marker came back without the payload's
shell wrapper, secret content came back, schema directive present,
etc.). `echo` = the marker came back, but so did the literal
payload syntax. Echo says "server reflects input"; vulnerable says
"server interpreted input dangerously."

**Q13. What's the difference between skipped and pass?**
`pass` = we sent the probe and the response was clean. `skipped` =
we never sent anything. A server with no shell-shaped tools gets
`skipped` on `command.shell_marker`, not `pass` — we have no
evidence about how it'd behave if it did have such a tool.

**Q14. What's the difference between error and skipped?**
`error` = probe ran, server returned `isError=True`, no signal
matched. `skipped` = probe never ran. Most `error` outcomes are
probe-design mismatches (matched by name regex but didn't satisfy
required args).

**Q15. When does suggestive fire?**
Only on `marker_echo` probes with `corroborate` set, when real_1
and real_2 disagree on whether the marker reflected. Indicates
intermittent behavior — caching, race, network blip. Rerun.

**Q16. Are findings sorted by severity?**
No. Console output shows them in scan order. JSONL is one finding
per line, scan order. Operators sort downstream.

**Q17. Does `vulnerable` mean "definitely exploitable"?**
No. It means "the server has a property that makes a real-world
attack feasible." Exploitability depends on who can reach the
endpoint, what the tool actually does at the application layer, and
whether the LLM consuming the server can be steered into calling
the vulnerable path. See `threat-models.md` for the per-class
attacker model.

### Threat models

**Q18. When you say "vulnerable" what does it mean concretely?**
Per class — see `threat-models.md`:
- `command.*`: shell injection → RCE as server process
- `path.*`: filesystem read → cross-tenant data exposure
- `response.*`: secret leak or LLM hijack via tool response
- `schema.*`: passive LLM steering before any tool call
- `auth.*`: anonymous tool access
- `authz.*`: BOLA → cross-tenant data + write escalation

**Q19. Are there false positives?**
Yes, by class:
- `directive_passthrough` fires on benign content that quotes injection examples.
- `secret_pattern` fires on placeholder strings (`password = "REPLACE_ME"`).
- `auth.no_credential` fires on intentionally-public servers (true positive in the matcher, not actionable).

**Q20. Are there false negatives?**
Many. Name-regex skips tools jakk could probe. Hand-authored
payloads miss bugs adjacent to the curated set. No fuzzing, so any
input space jakk doesn't explicitly target is invisible.

### Production / commercial use

**Q21. Can I scan a production MCP server?**
Only with `--safe`, and only after reading the threat model per
probe. Even safe probes call tools — if your tools have unintended
side effects (logging, notifications, billing meters), `--safe`
doesn't help. Default: scan staging first.

**Q22. Can I use this against a commercial MCP I don't own?**
Only under explicit authorization (bug-bounty scope, paid
engagement, vendor's published test fixtures). See
`depth-of-exposure-methodology.md` §2.

**Q23. Does it work behind OAuth?**
Yes — `--bearer TOKEN` or `--oauth-token-file PATH`. For more
complex auth (multi-step OAuth, mTLS, SAML), use
`--header KEY=VALUE` or proxy through a local stub.

### Comparisons

**Q24. Why not MCPHammer / breach-to-fix?**
Those are *target* labs, not scanners. jakk scans them. They're
complementary, not competing.

**Q25. What about MCPTox?**
Academic benchmark, 1,312 test cases. We haven't run jakk against
it yet, so we don't cite numbers. If we do run it, we'll report
honestly. Until then, MCPTox is not in the public materials.

**Q26. PromptFoo / Garak / PyRIT?**
Those test *language models* for adversarial prompts. jakk tests
*MCP servers* for protocol-level bugs. Different problem. A serious
threat model includes both.

### Limits and roadmap

**Q27. What's v0.3?**
Multi-required-arg filling, `--expect-auth` flag, deeper authz
probes (`tool_scope_breadth`, `id_predictability`,
`cross_tenant_write`), output dedup. The first real commercial
target.

**Q28. Will jakk ship as an MCP server eventually?**
Maybe as a v2 demo. Probably not as primary distribution. CLI
fits the actual user better. See ADR
`mcp-server-distribution-decision.md`.

**Q29. License?**
Apache 2.0. Same as the parent repo.

**Q30. Why now?**
MCP shipped late 2024, exploded through 2025; most major LLM
vendors and tool ecosystems ship MCP integrations. Adversarial-
research wave starting Q1 2026. Several target labs exist
(breach-to-fix, MCPHammer); the scanner category is empty.
Position-claiming window.

---

## 9 · The 30-second demo

```bash
# Bring up a vulnerable lab
docker compose -f examples/external_targets/_vendor/mcp-breach-to-fix-labs/docker-compose.yml \
  up -d git-command-injection-vulnerable git-command-injection-secure

# Scan vulnerable + secure side by side
jakk mcp scan --endpoint http://127.0.0.1:8008/mcp/stream --library jakk/library/mcp
jakk mcp scan --endpoint http://127.0.0.1:9008/mcp/stream --library jakk/library/mcp
```

Vulnerable shows the FLAG canary in evidence; secure shows clean
pass. That's the demo. Don't expand it.

---

## 10 · Where to look if you forget something

- Conceptual: `docs/jakk/2026-05-22_discovery.md`, `_v0.2_discovery.md`
- Threat models: `docs/jakk/threat-models.md`
- Live results: `docs/jakk/2026-05-22_smoke-report.md`
- Per-probe specs: `docs/jakk/tests/<id>.md`
- Depth methodology: `docs/jakk/depth-of-exposure-methodology.md`
- Decision records: `docs/jakk/mcp-server-distribution-decision.md`
- Self-security: `docs/jakk/system-hardening.md`
- Positioning: `docs/jakk/positioning.md`
- Source: `jakk/jakk/` (read order: `library.py` → `applies.py` → `scanner.py`)
