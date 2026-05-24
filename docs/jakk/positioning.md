---
date: 2026-05-23
status: technical positioning vs adjacent tools
audience: maintainers, contributors, future users evaluating jakk
scope: factual comparison — what jakk is, what it isn't, where it sits
       in the ecosystem of MCP security and AI red-teaming tools
---

# jakk positioning

Where jakk sits in the landscape, what it competes with, what it
composes with. No marketing tone — factual contrasts.

---

## 1 · The two-axis frame

Every MCP-security tool today sits somewhere on two axes:

```
                            (server-side attacks)
                                     │
              jakk ─────────►       │
              MCPHammer (target)    │
              breach-to-fix (target)│
              MCPTox (benchmark)    │
                                     │
   (deterministic) ─────────────────┼─────────────► (adaptive / LLM-driven)
                                     │
                                     │
                                     │
                                     │       ◄───── grafted
                                     │       ◄───── future agent-attack tools
                            (agent-side attacks)
```

- **X-axis**: deterministic single-call (left) vs adaptive multi-turn LLM-driven (right).
- **Y-axis**: attacks targeting the server (top) vs attacks targeting the LLM agent that consumes the server (bottom).

jakk sits firmly top-left: server-side, deterministic. grafted sits
bottom-right: agent-side, adaptive. The two are sibling tools, not
competitors. Together they cover both axes of MCP attack-surface
testing.

The "MCP attacks MCP" framing some discussions push is a third
position: jakk-as-MCP-server attacking other MCP servers. We've
declined that for v1 (see `mcp-server-distribution-decision.md`)
because it adds dogfooding cost without serving the actual user.

---

## 2 · jakk vs each adjacent tool

### 2.1 jakk vs grafted

| Dimension | jakk | grafted |
|---|---|---|
| Target | MCP server (infrastructure) | LLM agent (consumer of MCP / HTTP / browser tools) |
| Attacker model | Pre-authored payloads | LLM-driven adaptive, learns from victim responses |
| Probes | 11 hand-curated, single-call | Multi-turn campaigns, library + LLM-synthesized |
| Detection | Regex / substring / canary / schema scan | Oracle LLM + heuristic compliance classifier |
| Latency | <1s per probe | seconds-minutes per attack |
| LLM cost | Zero | Tokens per turn |
| Output | JSONL + console table | Per-engagement reports with cycle traces |
| Repository | `jakk/` (separate package) | `grafted/` (separate package, same repo) |

**Composition:** jakk's findings can seed grafted's StrategicMemory
(planned, v0.3+). Knowing "this server's `init_repo` tool is
shell-injectable" lets grafted skip discovery and jump to
multi-turn escalation experiments.

**Anti-claim:** jakk is NOT a stripped-down grafted. It targets a
different layer.

### 2.2 jakk vs MCPHammer (Praetorian)

MCPHammer is a deliberately vulnerable MCP server published by
Praetorian. Its purpose is to give attackers / defenders a known
target to test tooling against. ~29 ⭐ on GitHub at survey time
(May 2026).

| Dimension | jakk | MCPHammer |
|---|---|---|
| Role | Scanner | Target |
| Direction | Sends probes | Receives probes |
| Composition | jakk scans MCPHammer | MCPHammer is scanned by jakk |

They are complementary by construction. The recommended path: add
MCPHammer to `examples/external_targets/targets.yaml`, run the full
jakk library against it, document expected findings per probe. The
result becomes a built-in cross-target validation.

### 2.3 jakk vs breach-to-fix-labs (PawelKozy)

PawelKozy's repository ships 10 challenges, each with a
deliberately-vulnerable and a hardened variant of an MCP server.
~88 ⭐. Categories include path traversal, command injection,
hidden instructions in responses, SQL injection, log poisoning,
GitHub-issue injection.

| Dimension | jakk | breach-to-fix |
|---|---|---|
| Role | Scanner | Target lab |
| Already integrated? | Yes — `examples/external_targets/_vendor/mcp-breach-to-fix-labs/` |  |
| Probes that map 1:1 | shell_marker → ch08; prefix_bypass → ch02; directive_passthrough → ch03 | — |

Same composition shape as MCPHammer. breach-to-fix is already a
vendored checkout in our examples directory and the smoke-report
docs reference it heavily.

### 2.4 jakk vs MCPTox (academic)

MCPTox is an arxiv paper (2508.14925) publishing a benchmark of
1,312 adversarial test cases against MCP servers.

| Dimension | jakk | MCPTox |
|---|---|---|
| Output | Tool you run against a server | Benchmark dataset you measure tools against |
| Number of cases | 11 probes | 1,312 cases |
| Format | YAML library, deterministic matchers | Academic dataset |
| Have we run jakk against it? | **No** | — |
| Public claim possible? | **Not until we run it.** | — |

This is an explicit, important position: **we do not cite MCPTox
in any public materials until we have actually run jakk against the
dataset and reported the numbers honestly.** Mentioning MCPTox to
sound credible without running it is a category of dishonesty that
the security community catches and remembers.

If we do run MCPTox, the resulting numbers — including the
per-category breakdown of "jakk caught" vs "jakk missed" — get
their own discovery doc + smoke report. Until then, MCPTox is
acknowledged here for completeness, not used for marketing.

### 2.5 jakk vs PromptFoo / Garak / PyRIT

These are LLM-evaluation frameworks. PromptFoo tests prompt-string
behaviors via large case sweeps. Garak runs vulnerability scans
against language models (jailbreak attempts, harmful-output
elicitation). PyRIT (Microsoft) runs adversarial prompt testing
against LLM endpoints.

| Dimension | jakk | PromptFoo / Garak / PyRIT |
|---|---|---|
| Target | MCP server | Language model |
| Layer | Protocol + tool behavior | Prompt-completion behavior |
| Format | Single-call MCP probes | Prompt-completion test sweeps |
| Overlap | Near zero | — |

They don't compete. A serious threat model for an LLM application
includes BOTH categories: language-model evaluation (prompt-level)
AND server-side scanning (MCP / tool surface). jakk fills the
second category; the others fill the first.

### 2.6 jakk vs generic web scanners (Burp / nuclei / ZAP)

These are general-purpose HTTP / web app scanners. They can hit
any URL and check for common bugs (SQLi, XSS, SSRF, signature
matches).

| Dimension | jakk | Burp / nuclei / ZAP |
|---|---|---|
| Awareness of MCP | Native — knows `tools/list`, `tools/call`, session-id, etc. | None — sees JSON-RPC as opaque |
| MCP-specific probes | Yes (schema smuggling, directive passthrough, etc.) | Effectively no |
| Coverage of MCP protocol edge cases | Yes (session handling, initialize handshake, capability negotiation are scriptable) | Manual setup per case |
| Coverage of general web bugs | None | Extensive |

Composition: in a real engagement, run jakk for MCP-specific bugs
AND nuclei for generic web bugs. Neither replaces the other.

### 2.7 jakk vs vendor-side test fixtures (e.g. official MCP test suite)

Anthropic and the MCP SDK maintainers publish test fixtures for
spec compliance. These are tests that an MCP server author runs
during development.

| Dimension | jakk | Vendor test fixtures |
|---|---|---|
| Audience | Operators / red teams | Server authors |
| Goal | Find bugs in deployed servers | Verify spec conformance during development |
| Position | After-deployment scanning | Pre-deployment unit tests |

No overlap. A server that passes the vendor fixtures can still be
vulnerable to every probe in jakk's library — they test different
things.

---

## 3 · The "MCP attacks server" / "MCP attacks agent" split

Internal positioning that we should articulate clearly in every
external conversation:

- **"MCP attacks server"** — bugs in the MCP server's implementation.
  Path traversal, command injection, BOLA, schema smuggling, auth
  misconfig. **jakk's territory.**
- **"MCP attacks agent"** — the LLM agent consuming MCP is steered
  by malicious content that arrives via MCP tool responses. Indirect
  prompt injection at the agent layer; the server may be benign or
  blameless. **grafted's territory.**

A real-world MCP compromise often involves both: server-side bug
(jakk finds) + agent-side exploitation chain (grafted demonstrates).
A pair of tools that together model both halves is the durable
positioning. "MCP scanning MCP" is aesthetic; "server-side vs
agent-side" is structural.

---

## 4 · What jakk competes with for attention (not function)

There's a "first mover in adversarial MCP tooling" attention
window. Several tools are likely to land in this space over the
next 2-3 months. Position-claiming considerations:

| Concern | Position |
|---|---|
| Someone else ships an MCP scanner first | jakk's defensible claim is the **5+1-outcome taxonomy** (vulnerable/echo/pass/skipped/error/suggestive) and the **honest classification under corroboration**, not "we were first." |
| Someone else publishes a probe library | jakk's library is YAML-declarative and curated. Forks / extensions are encouraged. Library convergence is healthy. |
| Someone bolts MCP probes onto Burp / nuclei | Welcome. jakk's lane stays the same. |
| Someone runs MCPTox first | Their numbers are independent. We run our own when we run them. |
| Someone publishes a more comprehensive academic survey | We cite it. Independent academic work strengthens, not weakens, an open-source scanner's credibility. |

The position to defend is **technical honesty** (5+1 outcomes, the
explicit "we declined MCP-on-MCP" stance, the willingness to
document false-positive risks per probe class). Defending honesty
is more durable than defending firstness.

---

## 5 · What jakk is explicitly NOT

A list of things jakk is sometimes pitched as that we should
push back on:

- **"An MCP firewall."** No. We're a scanner. Firewalls operate in
  real-time against live traffic; jakk runs offline scans.
- **"A SIEM integration."** No. We emit JSONL; SIEMs can ingest it,
  but we don't ship an integration.
- **"An LLM-powered scanner."** No, deliberately. The whole point is
  zero LLM in the loop. (grafted's the LLM-driven sibling.)
- **"Production runtime protection."** No. Scan results inform
  hardening; jakk does not block traffic at runtime.
- **"A compliance tool."** No. Findings may inform compliance, but
  we don't map to any specific framework (PCI / SOC2 / etc.).
- **"A bug-bounty automation."** No. The depth-of-exposure
  methodology doc explicitly warns against this framing. jakk
  produces evidence; humans triage and disclose.

---

## 6 · Where to look if asked

- One-paragraph contrast vs grafted: see `launch-prep.md` §1
- Detailed FAQ comparing jakk to each tool: see `launch-prep.md` §8 Q24-26
- Why no MCP-server distribution: see `mcp-server-distribution-decision.md`
- Threat models per probe class: see `threat-models.md`
- Self-security posture: see `system-hardening.md`
