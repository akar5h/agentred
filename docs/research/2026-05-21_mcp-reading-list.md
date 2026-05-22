---
date: 2026-05-21
status: curated reading list — research agent output
scope: MCP protocol internals, adversarial attacks, prior-art tools
---

# Reading list for building jakk (May 2026)

Three sections: MCP internals, adversarial attacks (+ OWASP), and adjacent
must-reads for tool builders. Each entry has 2-3 sentences explaining
what's in it and why it matters for jakk.

---

## Section 1 — MCP inner workings, infrastructure, harness layer

### 1. MCP — Protocol Mechanics and Architecture
**Author:** Pradeep Loganathan | **Date:** 2025
**URL:** https://pradeepl.com/blog/model-context-protocol/mcp-protocol-mechanics-and-architecture/

Start here. The cleanest treatment of MCP as a layered system: the data
layer (JSON-RPC 2.0 messages, lifecycle, primitives) and the transport
layer (stdio, streamable HTTP, SSE deprecation) walked through with
wire-level examples. Covers the initialize handshake, capability
negotiation, protocol-version downgrade behaviour,
`tools/list`/`tools/call`/`resources/list`/`prompts/list` semantics,
structuredContent vs content blocks, notifications, and progress
reporting — exactly the surface area jakk needs to fuzz. The diagrams
distinguish the "MCP client" object inside a host from the host itself,
which matters when modelling trust boundaries. Read twice before writing
any jakk transport code; the second pass clarifies which fields are
mandatory and which are server-discretionary, which is where most
spec-conformance bugs hide.

### 2. How MCP Actually Works and Why FastMCP Is the Easiest Way to Use It
**Author:** Vunda AI Blog | **Date:** 2025
**URL:** https://www.vunda.ai/blog/fast-mcp-deep-dive

The best server-side architecture read. Walks through what happens
between a `@mcp.tool` decorator and a callable on the wire: how Pydantic
introspects the Python signature, derives the JSON Schema, registers it
in the tool registry, and how `tools/call` dispatches back into the
function with deserialised arguments. Critically, covers `mcp-session-id`
negotiation over streamable HTTP and how FastMCP handles the long-running
SSE channel concurrently with POST requests — important for jakk because
session handling is where many servers misbehave (session fixation,
replay, missing teardown). Since ~70% of MCP servers in the wild are
FastMCP-based, this internals story tells you what jakk will actually be
poking at.

### 3. Architecture Overview + Connect Claude Code to Tools via MCP
**Author:** Anthropic / MCP Spec | **Date:** 2025-11-25 spec rev
**URLs:** https://modelcontextprotocol.io/docs/learn/architecture and
https://code.claude.com/docs/en/mcp

The host-side companion. Treat as one read. The only canonical source
for how Claude Desktop / Claude Code / Cursor actually manage server
lifecycles: one client object per server, per-project approval
persistence, managed-mcp.json governance, `allowedMcpServers` /
`deniedMcpServers` enforcement, and the auto-approve categories that
turn into jakk's biggest attack surface. The "approval choices remembered
per project" mechanic is exactly the rug-pull window an attacker
exploits. Skim the high-level architecture page for the
connection-per-server model, then read the Claude Code MCP page closely —
the config schema, transport selection, and approval model documented
there is what hosts other than Anthropic's are converging on.

---

## Section 2 — Adversarial attacks on MCP

### 1. MCP Security Notification: Tool Poisoning Attacks
**Author:** Invariant Labs | **Date:** April 2025
**URL:** https://invariantlabs.ai/blog/mcp-security-notification-tool-poisoning-attacks

The foundational disclosure that coined "tool poisoning" and demonstrated
that tool descriptions and parameter-level `description` fields are an
executable attack surface — the LLM reads them as instructions even when
the user never sees them, and even when the tool is never invoked. The
PoC shows hidden instructions in metadata coercing the agent to read
`~/.ssh` and exfiltrate it via a benign-looking arg. Read this before
anything else in this section because every later writeup builds on its
threat model. For jakk, defines a whole catalog category: static analysis
of tool descriptions and JSON Schema description fields for injection
patterns. Invariant later joined Snyk Labs, so newer Snyk research is
the continuation of this line.

### 2. GitHub MCP Exploited: Accessing Private Repositories via MCP
**Author:** Invariant Labs | **Date:** May 26, 2025
**URL:** https://invariantlabs.ai/blog/mcp-github-vulnerability

The clearest real-world attack-chain writeup published to date and a
perfect end-to-end PoC. A malicious GitHub Issue in a public repo
containing prompt-injected content is read by an agent using the
official GitHub MCP server (14k stars); the agent then pivots to private
repos under the same OAuth token and exfiltrates contents into a PR or
comment on the public repo. Value for jakk is twofold: (a) it shows the
vulnerability is architectural — not in the server code — so static
scanning of server source code won't catch it, which sharpens jakk's
positioning around runtime/behavioural probing; (b) it gives a concrete
trifecta (untrusted input source, broad token scope, public write
capability) jakk can encode as a configuration-graph check across
multi-server setups.

### 3. Poison Everywhere: No Output From Your MCP Server Is Safe
**Author:** CyberArk Threat Research | **Date:** 2025
**URL:** https://www.cyberark.com/resources/threat-research-blog/poison-everywhere-no-output-from-your-mcp-server-is-safe

Extends the tool-poisoning thesis to every output channel: nested
injection inside property-level `description` fields (not just the
top-level tool description), poisoned tool *responses* (the result
returned to the LLM), error messages, and even resource contents.
CyberArk demonstrate that mitigations focused on top-level tool
descriptions miss the bulk of the attack surface. The highest-density
read for building jakk's payload catalogue — most public scanners only
look at top-level descriptions, so coverage of nested `description`
fields, response payloads, and CallToolResult content/structuredContent
fields is differentiating. Pair with Elastic Security Labs' "MCP Tools:
Attack Vectors" for cross-validation.

### 4. OWASP MCP Top 10
**Author:** OWASP Foundation | **Date:** 2025, ongoing
**URL:** https://owasp.org/www-project-mcp-top-10/

The reference taxonomy jakk should map its checks to. Unlike the OWASP
LLM Top 10 (too prompt-string focused) or the new Agentic Apps Top 10
(broader than MCP), the MCP Top 10 is purpose-built: MCP01 Token
Mismanagement & Secret Exposure, MCP03 Command Injection, MCP04 Supply
Chain Attacks, MCP07 Insufficient Auth/Authz, plus categories for
context spoofing, prompt-state manipulation, and covert channels. For
jakk's positioning, having each catalog item tagged with an
MCP-Top-10 ID is a low-cost credibility signal that mirrors how nuclei
tags templates with CVEs and OWASP IDs. Also read the companion OWASP
Top 10 for Agentic Applications 2026
(https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/)
for upstream categories like Agent Goal Hijack and Tool Misuse.

---

## Section 3 — Other must-reads for tool builders

### 1. Your MCP Server Has No Tests. Here Are 4 Patterns to Fix That.
**Author:** Klement Gunndu (DEV Community) | **Date:** March 26, 2026
**URL:** https://dev.to/klement_gunndu/your-mcp-server-has-no-tests-here-are-4-patterns-to-fix-that-2k59

The four patterns map almost 1:1 onto jakk catalogue check classes:
schema-stability tests, tool-roundtrip tests, error-path tests, and
resource/prompt rendering tests. Uses the FastMCP 2.x in-memory `Client`
to drive the server through real MCP protocol calls without spinning up
an LLM, which is exactly the substrate jakk needs for deterministic,
CI-friendly checks. Key insight: MCP servers are pure functions consumed
by non-deterministic clients, so the test boundary belongs at the
protocol, not at the LLM — same boundary jakk should sit at.

### 2. Testing MCP Servers: The Five Gates Between Demo and Production
**Author:** Guy Ernest (AWS Heroes / DEV Community) | **Date:** 2025-2026
**URL:** https://dev.to/aws-heroes/testing-mcp-servers-the-five-gates-between-demo-and-production-2inf

Frames MCP server maturity as five sequential gates — protocol
conformance, workflow correctness, scale, security, and score-impact —
and matches each gate to tooling (MCP Inspector for manual exploration,
scenario tests in CI for regression, loadtest for capacity, pentest for
security validation). The security gate is the wedge: existing tooling
handles gates 1-2 well but security is under-served. Also implicitly
argues against LLM-in-the-loop testing for protocol-layer issues, which
validates jakk being a deterministic, catalog-driven scanner rather
than a fuzzing harness that needs an LLM to interpret results.

### 3. We Built the Security Layer MCP Always Needed (Trail of Bits)
**Author:** Trail of Bits Blog | **Date:** July 28, 2025
**URL:** https://blog.trailofbits.com/2025/07/28/we-built-the-security-layer-mcp-always-needed/

The release post for `mcp-context-protector`, a defensive wrapper. Worth
reading not because jakk is a wrapper (it isn't — it's a scanner), but
because Trail of Bits enumerates the classes of attack their proxy must
defend against (line-jumping via tool descriptions, ANSI escape code
attacks, prompt injection via server output, rug-pulls via
trust-on-first-use pinning). That enumeration is a near-perfect dual to
jakk's offensive catalog: anything the wrapper pins or sanitises is
something jakk should probe. Pair with the same blog's "Hijacking
Multi-Agent Systems in Your PajaMAS"
(https://blog.trailofbits.com/2025/07/31/hijacking-multi-agent-systems-in-your-pajamas/)
for multi-server/multi-agent shadowing semantics.

### 4. Introducing FastMCP 3.0 + FastMCP 2.13: Storage, Security, and Scale
**Author:** Jeremiah Lowin (Mostly Harmless) | **Date:** Feb 2026 + late 2025
**URLs:** https://jlowin.dev/blog/fastmcp-3 and https://jlowin.dev/blog/fastmcp-2-13

Read as one. FastMCP 3.0 post defines the framework's three primitives
— Components, Providers, Transforms — and explains why tool
transformation, middleware, and auth backends are now first-class.
Foundational for jakk because the vast majority of servers jakk will
scan are FastMCP-based, and the 3.0 middleware/transform pipeline is
precisely where defensive controls (or attacker-friendly
misconfigurations) live. 2.13 introduces FastMCP's storage and security
primitives — secret backends, OAuth/JWT auth, scopes — so jakk can
build checks like "is OAuth required for this tool?", "are scopes
correctly enforced server-side?". Lowin's `Your MCP Server Is Bad (and
You Should Feel Bad)` talk (AI Engineer Code Summit 2025,
https://www.youtube.com/watch?v=UQjAZrTM0MI) is the spoken-word version.

### 5. Nuclei (ProjectDiscovery) — README + Architecture
**Author:** ProjectDiscovery | **Date:** ongoing
**URL:** https://github.com/projectdiscovery/nuclei

Not an "MCP" piece, but the most relevant prior art for jakk's
positioning. Internalise: YAML-DSL catalog format, severity taxonomy,
matchers/extractors separation, template signing/trust model, the
contributor flywheel (8000+ templates), and the CLI surface (rate-limit,
concurrency, output formatters). jakk should borrow the catalog-as-data
architecture, the matcher/extractor split (because MCP probes also need
"send this payload, then assert this property of the response"), and
the OSS posture (Apache 2.0, no open-core trap, community templates).
Pair with sqlmap's docs (https://sectools.org/tool/sqlmap/) for
fine-grained probe control patterns — the `--level`/`--risk` knobs are
a good model for jakk's "how aggressively should I probe this server"
controls.

---

## Sources

- [Pradeep Loganathan — MCP Protocol Mechanics and Architecture](https://pradeepl.com/blog/model-context-protocol/mcp-protocol-mechanics-and-architecture/)
- [Vunda AI — FastMCP Deep Dive](https://www.vunda.ai/blog/fast-mcp-deep-dive)
- [Anthropic — MCP Architecture Overview](https://modelcontextprotocol.io/docs/learn/architecture)
- [Anthropic — Connect Claude Code to Tools via MCP](https://code.claude.com/docs/en/mcp)
- [Invariant Labs — Tool Poisoning Attacks (April 2025)](https://invariantlabs.ai/blog/mcp-security-notification-tool-poisoning-attacks)
- [Invariant Labs — GitHub MCP Exploited (May 2025)](https://invariantlabs.ai/blog/mcp-github-vulnerability)
- [CyberArk — Poison Everywhere](https://www.cyberark.com/resources/threat-research-blog/poison-everywhere-no-output-from-your-mcp-server-is-safe)
- [Elastic Security Labs — MCP Tools: Attack Vectors](https://www.elastic.co/security-labs/mcp-tools-attack-defense-recommendations)
- [OWASP MCP Top 10](https://owasp.org/www-project-mcp-top-10/)
- [OWASP Top 10 for Agentic Applications 2026](https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/)
- [Klement Gunndu — Your MCP Server Has No Tests](https://dev.to/klement_gunndu/your-mcp-server-has-no-tests-here-are-4-patterns-to-fix-that-2k59)
- [Guy Ernest — Testing MCP Servers: The Five Gates](https://dev.to/aws-heroes/testing-mcp-servers-the-five-gates-between-demo-and-production-2inf)
- [Trail of Bits — We Built the Security Layer MCP Always Needed](https://blog.trailofbits.com/2025/07/28/we-built-the-security-layer-mcp-always-needed/)
- [Trail of Bits — Hijacking Multi-Agent Systems in Your PajaMAS](https://blog.trailofbits.com/2025/07/31/hijacking-multi-agent-systems-in-your-pajamas/)
- [Jeremiah Lowin — Introducing FastMCP 3.0](https://jlowin.dev/blog/fastmcp-3)
- [Jeremiah Lowin — FastMCP 2.13: Storage, Security, and Scale](https://jlowin.dev/blog/fastmcp-2-13)
- [Jeremiah Lowin — Your MCP Server Is Bad (AI Engineer Summit talk)](https://www.youtube.com/watch?v=UQjAZrTM0MI)
- [Nuclei (ProjectDiscovery GitHub)](https://github.com/projectdiscovery/nuclei)
- [sqlmap](https://sectools.org/tool/sqlmap/)
- [Simon Willison — MCP Has Prompt Injection Security Problems](https://simonwillison.net/2025/Apr/9/mcp-prompt-injection/)
