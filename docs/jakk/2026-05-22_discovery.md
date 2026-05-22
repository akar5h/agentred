---
date: 2026-05-22
status: discovery — synthesis of jakk v0.1 design + smoke results
scope: everything learned building and running jakk to date
related:
  - docs/jakk/README.md (catalog)
  - docs/jakk/2026-05-22_smoke-report.md (per-run results)
  - docs/jakk/tests/*.md (per-test pages)
---

# jakk discovery doc

What we set out to find, what we actually found, and what we still
don't know. This is *not* a status report or a roadmap — it's the
distillation of every decision and surprise so far, written so
someone (including future-me) can pick up the work without rerunning
the conversation.

---

## 1 · What jakk is (and what it is deliberately not)

| | jakk | grafted |
|---|---|---|
| Attacker | deterministic payload table | adaptive LLM with memory |
| Turns | single-shot per probe | multi-turn with feedback |
| Target | MCP endpoint only | full agent (HTTP / MCP / AgentDojo) |
| Detection | substring / regex / canary echo / schema scan | LLM oracle + heuristics |
| Latency | <1s per probe | seconds–minutes per attack |
| Cost | zero LLM tokens | LLM tokens per turn |

**Design intent:** jakk catches the bugs you can catch *without* an
LLM in the loop, fast, repeatably, and at near-zero cost. grafted's
job is the hard half — bugs that only show up under adaptive
pressure. They share a target class (capability-boundary attacks
against MCP), and jakk's findings can prime grafted's
StrategicMemory in the same engagement.

This split is the load-bearing decision that determines what's
in-scope. Anything that needs an LLM judgement to detect is out of
scope for jakk; anything that needs multi-turn state to *exploit* is
out of scope. Both belong to grafted.

---

## 2 · Architecture decisions and why

| Decision | What we picked | Why | Alternatives considered |
|---|---|---|---|
| Package layout | Top-level `jakk/` with own `pyproject.toml`, separate from `grafted/` | Will eventually ship standalone; clean separation of scanner-tool vs research-harness; independent dep set | In-tree subpackage under `grafted/`; `grafted` subcommand only |
| MCP client | `fastmcp.Client` (v3.x) | Built-in streamable-HTTP + SSE + stdio + session-id handling; widely deployed (~70% of MCP servers are FastMCP-based, so SDK matches likely target surface) | Official `mcp` Python SDK (less idiomatic API); hand-rolled httpx JSON-RPC (more code, useful for fuzzing the transport itself) |
| Library format | YAML, one file per test | Human-readable; easy diff in PRs; per-test docs map 1:1 to YAML files | JSON suite files (matches existing `grafted/attack/library/tools/*.json` shape, but designed for multi-turn LLM attacks not MCP probes) |
| Test classification | 5-outcome enum (`vulnerable`, `echo`, `pass`, `skipped`, `error`) | Binary fired/not-fired hides real distinctions: input reflection ≠ shell expansion; "no tool matched" ≠ "tool matched but failed" | Boolean `fired` only (what we shipped first; replaced after smoke run forced the distinction — see §4) |
| Tool selection | `applies_to.tool_name_regex` (`re.search`) | Conservative — low false-positive rate, easy to reason about | Aggressive (try every tool with every probe); schema-shape matching (more powerful, more complex) |
| Matchers | Pluggable registry (`substring`, `regex`, `marker_echo`, `secret_pattern`, `directive_passthrough`, `schema_field`) | Each matcher carries its own evidence semantics; new ones don't require core changes | Single regex-based matcher (less expressive); LLM-judge matcher (would violate the "no LLM" design intent) |

---

## 3 · Live findings — what the smoke actually demonstrated

Target inventory exercised so far:

| Target | Port | Class | Result |
|---|---|---|---|
| breach-to-fix ch08 git-command-injection-vulnerable | 8008 | CVE GHSA-3q26-f695-pp76 | jakk fires `shell_marker` (high) + `secret_file_read` (critical) |
| breach-to-fix ch08 git-command-injection-secure | 9008 | hardened variant | clean (0 vulnerable, 0 false-positive) |
| breach-to-fix ch02 filesystem-bypass-prefix-vulnerable | 8002 | CVE-2025-53110 | jakk fires `prefix_bypass` (high) + `canary_file_read` (critical) |
| breach-to-fix ch02 filesystem-bypass-prefix-secure | 9002 | hardened variant | clean |

Findings that came out of running these (beyond "jakk works"):

**3.1 Payload shape matters more than payload content for command-injection.**
The first version of `secret_file_read` used `$(cat /file)` substitution. Result on ch08: git's argv parser tripped on the multi-line file contents and printed a usage banner instead of the secret. The fix was switching to `;`-chained commands. **Lesson:** for any command-injection probe targeting a tool that runs an external binary, prefer command chaining over substitution. Substitution pollutes the host command's positional args.

**3.2 A bypass probe and an impact probe are not the same thing.**
`mcp.path.prefix_bypass` fires on `list_directory_contents` (returns the directory entries — strong evidence of both bypass and content disclosure) and also fires on `read_file_contents` (returns "is a directory, not a file" — weak evidence: bypass confirmed, exfiltration didn't complete). The matcher said "fired" both times, but the *value* of the two findings differs enormously. We split this into `prefix_bypass` (sink probe) and `canary_file_read` (impact probe). Same pattern as `shell_marker` → `secret_file_read`. **Pattern:** keep sink and impact probes distinct; the operator gets to see *what was bypassed* and *what was exfiltrated* as separate evidence.

**3.3 `marker_echo` "echo-only" branch is theoretically correct but live-unverified.**
The classifier downgrades `vulnerable` → `echo` when the response contains both the marker AND the surrounding shell syntax. Neither ch08-secure nor ch02-secure produced that response shape — they reject input outright, no echo. We have unit-test coverage of the branch but no live target that exercises it. **Gap:** until we find or build a server that reflects unknown input verbatim in an error message, we don't know the matcher behaves correctly in the wild for this class.

**3.4 `applies_to.tool_name_regex` is brittle but acceptable.**
It picks tools by *name*, not *capability*. A path-traversal tool called `fetch` won't match `mcp.path.prefix_bypass`'s current regex. Conservative on purpose (no false positives from wild matches), but it silently skips tools jakk could in principle probe. **Lesson:** name-regex is the right v0 default — false positives are louder than false negatives at low coverage. But it's a known ceiling.

**3.5 Required-args filter is necessary, not optional.**
First version of `secret_overshare`/`directive_passthrough` matched ch02's `read_file_contents` by name regex, then called it with `{}` (no args), got `isError=True`, and surfaced 4 `error` outcomes per ch02 endpoint. None of those were findings — they were probe-design bugs. The fix (`applies_to.require_no_required_args: bool`) eliminated the noise. **Pattern:** any probe that calls with empty arguments must filter out args-required tools at selection time, not after the failed call.

**3.6 Side-effect-free schema probe is the highest-leverage class.**
`mcp.schema.description_smuggling` runs from a single `tools/list` call. Zero tool invocations. Zero side effects. Catches a critical class (tool poisoning via description, the Invariant Labs writeup pattern). It should be the only probe that's safe to run unconditionally against any server, including production. **Implication:** the eventual `--safe` flag should at minimum include this one.

---

## 4 · Bugs and edge cases caught during development

These were found by either the smoke run or the post-smoke audit. All
are documented + tested + fixed:

| Class | Issue | How surfaced |
|---|---|---|
| matcher honesty | Binary `fired` couldn't distinguish input reflection from shell expansion | First ch08 smoke showed `shell_marker` firing on vulnerable target with marker expanded; would have also fired on a hypothetical server that echoes input. Forced the 5-outcome taxonomy. |
| payload design | `$(cat …)` substitution + multi-line file = host command argv overflow | First `secret_file_read` smoke returned git's usage banner, not the secret. Fixed via `;` chaining. |
| probe scope | bypass-with-error-message vs bypass-with-content-disclosure | ch02 smoke showed `prefix_bypass` matcher firing on `read_file_contents` only via the directory name in an error string. Led to `canary_file_read` as the impact-tier sibling. |
| library schema | `tool_name_regex` not validated at load time | Audit found `re.compile` would crash at scan-time on malformed YAML. Added Pydantic `field_validator`. |
| scanner behavior | `__first_string_arg__` on a tool with no string arg silently dropped the key | Audit. Fixed by raising explicit exception → scanner emits `skipped` finding. |
| applies_to coverage | No way to filter args-required tools | ch02 smoke produced 4 `error` rows per endpoint. Added `require_no_required_args` boolean. |

Documented-not-fixed (risks accepted, listed in §8.7 of smoke report):

- Evidence text duplicated when fastmcp returns both `content[].text` and `structured_content`.
- `directive_passthrough` would FP on benign `"System: ready"` log lines.
- Library loader ignores `*.yml` (only `*.yaml`).
- CLI has no `--list-tests`, no `--max-tools-per-test`, no OR support in `--owasp`.

---

## 5 · What we haven't tested (the honest gap list)

These should be visible when assessing what "jakk v0.1 works" actually
means. A probe being in the library is not evidence it has *ever* fired
against a true positive.

| Probe | True-positive demonstrated? | False-positive risk verified? | Notes |
|---|---|---|---|
| `mcp.command.shell_marker` | yes (ch08 :8008) | partial — `echo` branch unfired live | confident |
| `mcp.command.secret_file_read` | yes (ch08 :8008) | not exercised | confident |
| `mcp.path.prefix_bypass` | yes (ch02 :8002) | not exercised against echo-style server | confident |
| `mcp.path.canary_file_read` | yes (ch02 :8002) | not exercised | confident |
| `mcp.response.secret_overshare` | **no live target** | unknown | needs team-kb-mcp or seeded canary server |
| `mcp.response.directive_passthrough` | **no live target** | high — heuristic FPs likely on log-bearing tools | needs ch03 or ch05 target |
| `mcp.schema.description_smuggling` | **no live target** | unknown | needs server with poisoned tool description |

Surfaces not exercised at all:
- **Transports**: only streamable-HTTP. No stdio, no SSE.
- **Auth**: no token-protected endpoint yet tested. jakk has no `--bearer` / `--header` flags today.
- **Side-effecting tools**: every probe assumes idempotent calls. No `--safe` flag yet.
- **Schema fuzzing**: no probe currently generates inputs from `inputSchema` — all payloads are hand-authored.
- **Cross-tenant / authz**: no probe class for "tool returns object belonging to another tenant/user" — the most common commercial-MCP bug class.
- **Session handling**: no probe for `mcp-session-id` fixation, replay, or missing teardown.
- **Multi-tool servers**: largest server tested has 2 tools. No N-tool blowup measured.

---

## 6 · Open design questions

These are things I'd want a second opinion on before locking down:

**6.1 Should `applies_to` be name-based or schema-based?**
Name regex is brittle but fast and gives low FP. Schema-shape matching (e.g. "any tool with a string arg whose schema description mentions 'path' or 'file'") would catch more. Trade-off is implementation complexity + a new failure mode (schema description matching is itself heuristic and FP-prone). Current call: stay name-based for v0, revisit when we have a target that obviously misses.

**6.2 How aggressive should probe fan-out be?**
A server with 30 matching tools today fires 30 calls per probe. Defensible against ch02/ch08 (≤2 matching tools). Will become a problem against a real workspace MCP. Options: hard cap (`--max-tools-per-test 3`), priority ranking (run against shortest-named/simplest-schema first, stop on first vulnerable), or operator opt-in (`--exhaustive`). No call yet.

**6.3 Is the 5-outcome taxonomy stable?**
`vulnerable / echo / pass / skipped / error` covers what we've seen. Possible missing labels:
- `inconclusive` — probe ran, response was ambiguous (e.g. server returned a redacted version of the secret)
- `suggestive` — single hit on a corroboration-required probe (see §7.1)
- `unauthorized` — server returned 401/403; probe couldn't run (auth-aware probes)

Adding labels is cheap; removing them is hard. Leaning toward letting v0.2 produce evidence for a 6th label before adding it.

**6.4 Where does authz testing live?**
Cross-tenant reads (the most common commercial-MCP bug class) need *two* authenticated identities — call as Alice, see if Bob's data comes back. That's a fundamentally different probe shape: stateful, two-credential, requires baseline data. Could fit in jakk (`mcp.authz.cross_tenant_read`) or could be a sibling tool. Argues for jakk if the probe still resolves in one logical scan; argues against if it needs orchestration.

**6.5 What's the relationship to grafted's StrategicMemory?**
If jakk runs first and finds `mcp.command.shell_marker` firing on `init_bare_repository`, grafted's adaptive loop should know to try multi-turn escalations on that specific tool. Mechanically: jakk's JSONL → grafted's StrategicMemory seed file. Not built yet, but it's the integration point that makes the two tools more than the sum of their parts.

---

## 7 · Patterns that emerged worth keeping

**7.1 Sink probe → impact probe pair.** Both `mcp.command.*` and `mcp.path.*` follow this shape: one cheap probe that proves the sink exists, one targeted probe that proves what an attacker could do with it. Keep this for future classes (e.g. SSRF: `mcp.ssrf.callback_marker` → `mcp.ssrf.cloud_metadata_read`).

**7.2 Per-run markers, not static ones.** Every command-injection probe gets a fresh 4-byte hex marker per call. Eliminates marker collisions across probes and runs; keeps evidence high-entropy. This is the same trick LDAP-injection scanners and SSRF scanners use.

**7.3 Conservative `applies_to` + many narrow probes > permissive `applies_to` + few wide probes.** The library should be a long list of cheap, specific tests, not a small list of clever generic ones. Easier to write per-test docs, easier to triage findings, easier to expand the catalog.

**7.4 Outcome ≠ severity.** A high-severity test that produces `pass` is not a high-severity finding. The console renderer and JSONL keep these orthogonal. Don't collapse them — operators want both "how bad is this class" and "did we find it" as separate signals.

**7.5 Per-test docs as load-bearing artifacts.** `docs/jakk/tests/<id>.md` is the source of truth for what the test means, not the YAML. The YAML is the *executable*; the doc is the *spec*. When the YAML changes (payload swap, regex tightening, etc.), the doc must follow.

---

## 8 · Forward agenda (priority order)

This isn't a roadmap — it's the next-step ranking based on what would
move the project the furthest toward "useful against commercial MCPs."

1. **Auth + transport flags** — `--bearer`, `--header`, `--oauth-token-file`. Without these, jakk literally cannot run against any commercial target. Largest gating item.
2. **`side_effect` classification + `--safe` flag** — needed before any scan that might post messages / create resources / send notifications.
3. **`mcp.authz.cross_tenant_read` probe class** — highest-value missing class for commercial MCPs.
4. **Corroboration logic** — differential probe + negative canary for the existing `mcp.command.*` family. Cuts FP rate before we leave the lab.
5. **One real target** — pick GitHub MCP (docker container available, scope clear via bug bounty) and run the hardened library. Find out what we don't know we don't know.
6. **Dedup `_flatten_content` output** — small but quality-of-life.
7. **Schema-shape `applies_to`** — only if §1 finds we're missing matches in practice.

What we explicitly *should not* do next:
- Random schema fuzzing (mountain of FPs; existing tools like PromptFoo/Garak don't help here either).
- LLM-judge matchers (violates the design intent; that's what grafted is for).
- A web UI (premature; CLI + JSONL is enough until findings volume justifies it).

---

## 9 · Glossary

| Term | Meaning in jakk |
|---|---|
| **Probe** | A single YAML test in `jakk/library/mcp/`. |
| **Sink probe** | A probe that proves a dangerous input reaches a dangerous code path (e.g. `shell_marker`). |
| **Impact probe** | A probe that proves the dangerous code path leaks something an attacker wants (e.g. `secret_file_read`). |
| **`fired`** | Boolean — matcher returned True. Says nothing about whether the finding is exploitable. |
| **`outcome`** | Refined verdict — one of `vulnerable / echo / pass / skipped / error`. The actual taxonomy operators read. |
| **`vulnerable`** | Probe found evidence the response exceeded simple input reflection (file contents, expanded substitution, hidden schema directives, …). |
| **`echo`** | Marker reflected back alongside the surrounding payload syntax — input was returned but not interpreted. NOT exploitable on its own. |
| **`pass`** | Probe ran, response was clean. |
| **`skipped`** | Probe never ran — no compatible tool, or payload couldn't be resolved against the tool's schema. |
| **`error`** | Probe ran, server returned `isError=True` AND no signal matched. Indicates either an unhandled exception or a probe-design mismatch (the latter is what `require_no_required_args` fixes). |
| **`applies_to`** | YAML field deciding which tools on the server the probe fires against. Includes `tool_name`, `tool_name_regex`, `min_string_args`, `require_no_required_args`, `none`. |
| **`__first_string_arg__`** | Reserved key in `payload.arguments`. Resolves at scan time to the first string-typed parameter in the matched tool's `inputSchema`. |

---

## 10 · Where to look next

- `jakk/jakk/` — implementation. Start with `library.py` (schema) → `applies.py` (filter) → `scanner.py` (orchestration).
- `jakk/library/mcp/` — the 7 v0.1 probes.
- `docs/jakk/tests/<id>.md` — per-test specs.
- `docs/jakk/2026-05-22_smoke-report.md` — every concrete number from live runs (ch08 + ch02, before and after the audit fixes).
- `examples/external_targets/targets.yaml` — registry of vulnerable + secure docker compose targets.
- `examples/external_targets/_vendor/mcp-breach-to-fix-labs/` — the lab source (do not modify; vendor checkout).

For anyone joining: the fastest path to understanding what jakk does
is to bring up `git-command-injection-vulnerable` on :8008 and run
`jakk mcp scan --endpoint http://127.0.0.1:8008/mcp/stream --library
jakk/library/mcp`. The output explains itself.
