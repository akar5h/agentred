---
date: 2026-05-23
status: progress snapshot + next-attack plan
audience: the creator (AI eng/dev, not primarily a security specialist)
scope: everything built/decided in the jakk-v0.2 line + the github-mcp finding + how we go deeper
---

# jakk — progress snapshot & next attack (2026-05-23)

Plain-language running record. What exists, what we decided and why,
what the live results are, and the plan for the deeper attack on the
github-mcp-server finding.

---

## 1 · What jakk is (one paragraph)

A scanner for MCP servers that talk over HTTP. You point it at a
server's URL, it lists the server's tools, fires a small library of
canned adversarial probes at the ones it understands, and tells you —
per probe — whether the server looks `vulnerable`, merely reflected
your input (`echo`), passed clean (`pass`), wasn't applicable
(`skipped`), or errored (`error`). No LLM involved; it's deterministic
pattern-matching. Its sibling `grafted` does the LLM-driven multi-turn
attacks; jakk does the fast deterministic server-side checks.

---

## 2 · What we built (chronological)

| Phase | What landed | Commit |
|---|---|---|
| v0.1 | 7 probes (command-injection, path-traversal, response leaks, schema poisoning), 5-outcome taxonomy, FastMCP HTTP client, JSONL output | `2a1ff15` |
| v0.2 Day 1–2 | Auth flags (`--bearer`, `--oauth-token-file`, `--header`), `side_effect: safe\|unsafe` + `--safe`, 3 auth-misconfig probes (`auth.*`) | `c8477a6` |
| v0.2 Day 3 | `mcp.authz.cross_tenant_read` — two-credential confused-deputy probe | `a7c2340` |
| v0.2 Day 4 | Corroboration (3-call differential + negative canary) for marker_echo probes; new `suggestive` outcome | `d0a9c73` |
| docs pass | threat-models.md, per-test threat sections, README v0.2 | `1f8cfd5` |
| methodology | depth-of-exposure playbook + ch01-extended lab (BOLA read+write) | `d8b096a` |
| launch dossier | launch-prep, mcp-server-distribution ADR, system-hardening, positioning, ch01 experiment writeup | `7770081` |
| C+ | schema-aware arg-kind resolution (`target_arg_kind`, `__target_arg__`) — probes target args by semantic role, generalize across servers | `802cddb` |

11 probes, 110 unit tests, branch `jakk-v0.2` (pushed as `akar5h`).

---

## 3 · Key decisions and why

| Decision | Why |
|---|---|
| **jakk is HTTP-only; stdio is out of scope** | stdio MCP servers are single-user local subprocesses — no transport auth, no tenants. jakk's auth + authz probes (half the library) are *meaningless* there. The real bugs live in multi-tenant hosted HTTP servers. HTTP-only isn't a gap, it's the threat model. (`scope-decision.md`) |
| **Don't ship jakk as an MCP server** | "MCP scanning MCP" is a catchy framing but adds a dogfooding tax (8 of 11 probes would apply to jakk-as-server) for an audience (security engineers) that lives in a terminal, not an LLM chat. CLI is the right interface. (`mcp-server-distribution-decision.md`) |
| **C+ over hardcoding** | Probes target args by *role* (`path`, `query`, ...) not by literal name or per-vendor YAML, so one library works against any server. (`2026-05-22_v0.2_discovery.md` §11) |
| **"Vulnerable" is per-class, not generic** | Each probe class has its own threat model and harm. We always answer "vulnerable to what, harmful to whom." (`threat-models.md`) |
| **Honest skipped > pretended pass; verify every vulnerable by hand** | A scanner firing is a lead, not proof. |

---

## 4 · Live results to date

### 4.1 breach-to-fix labs (deliberately-vulnerable, our calibration set)

| Endpoint | Variant | vulnerable | pass | skipped | error |
|---|---|---:|---:|---:|---:|
| `:8008` git-cli | vuln | 4 | 3 | 4 | 0 |
| `:9008` git-cli | secure | 2 (auth*) | 5 | 4 | 0 |
| `:8002` filesystem | vuln | 5 | 1 | 6 | 0 |
| `:9002` filesystem | secure | 2 (auth*) | 4 | 6 | 0 |
| `:8001` Asana CRM | vuln | 3 | 1 | 5 | 1 |
| `:9001` Asana CRM | secure | 2 (auth*) | 2 | 5 | 1 |

\* the labs ship with NO auth by design, so the auth probes correctly
fire on every variant — true positives on intentionally-open servers.

### 4.2 github-mcp-server (first REAL production target, HTTP read-only mode)

```
23 tools exposed.  Full scan: pass=11  error=7  skipped=1  vulnerable=1
```

- **pass=11** including the three results that matter: `auth.no_credential` → 401 (rejected), `auth.invalid_token` → 400 (rejected), `schema.description_smuggling` → clean. First time jakk's auth probes produced TRUE NEGATIVES against a correctly-built server — proof they're not always-fire noise.
- **vulnerable=1**: `auth.wrong_prefix` — server accepts the token without the `Bearer ` scheme prefix. Verified by hand (4 header variants). **Low severity** — spec-conformance laxity, not an auth bypass (the token is still validated). Full analysis in `2026-05-23_github-mcp-coverage-run.md` §3.
- **error=7**: the valuable result. The path/command probes errored on `missing required parameter: owner`. C+ correctly put the payload in `path`, but multi-arg tools like `get_file_contents(owner, repo, path)` need `owner` + `repo` filled with valid values too. **Coverage gap → v0.3 priority #1: context-arg supply.**

---

## 5 · The finding we're about to attack deeper

**`auth.wrong_prefix` on github-mcp-server.**

Plain version: the server accepts your auth token even when the
`Authorization` header is formatted wrong — no `Bearer` word, or
lowercase `bearer`. It still rejects a *missing* or *garbage* token,
so it's loose about the *format* but strict about the *token itself*.

Why it's weak on its own: an attacker needs a valid token to benefit,
and a valid token already works the correct way. The sloppy format
grants nothing extra.

Where it could become real: a **parser differential**. If a security
gateway sits in front of the server and decides "allow / deny" based
on the `Authorization` header — but the gateway and the server
*disagree* on what counts as a valid header — an attacker can craft a
request that slips past the gateway's check while the server still
honors it. That gap is the actual vulnerability. See §6 for how we'd
test it.

---

## 6 · The wrong_prefix finding — why "go deeper" mostly dead-ends, and what doesn't

We interrogated "do a deeper attack on the finding" and concluded:
**building our own gateway to chase a parser-differential is circular
and proves nothing.** Recording the reasoning so we don't relitigate it.

### Why the obvious "deep" move is a trap

The lax-scheme finding only becomes a *real* auth bypass if a gateway
in front of the server validates the `Authorization` header
differently than the server does (a "parser differential"). The
tempting move: stand up a gateway and hunt for the split.

The problem: **if we author the gateway's rules, we're constructing
the conclusion.** Invent a gateway that rejects bare-token, find that
the server accepts bare-token, declare a "bypass" — we designed the
gap into existence. That's the same self-validation trap as building a
vulnerable server and then proving it's vulnerable, one layer up.

```
  invent gateway rules ──► find a header that splits them
          │                          │
          └──► we designed the split into existence ◄──┘
                    = proves nothing real
```

### When a gateway is legitimate (and why it still mostly doesn't help here)

A gateway is real evidence ONLY if it's an off-the-shelf gateway
running default/documented config — something thousands of people
actually deploy (oauth2-proxy, nginx's documented auth snippet, Kong's
bearer plugin). If *that* disagrees with the server, it's a real risk
for everyone running the combo.

But the deflating catch: **most gateways don't inspect the
`Authorization` header at all by default** — nginx, Envoy, plain
reverse proxies pass it through untouched and let the origin decide.
There's nothing to disagree about. The ones that *do* inspect bearer
tokens are configured per-deployment, so there's no canonical "the
gateway" to test against generically.

### The honest verdict

| Approach | Verdict |
|---|---|
| Build our own gateway with invented rules, find the split | ❌ Circular. Proves nothing. The trap. |
| Run a real off-the-shelf gateway at defaults | ⚠️ Legitimate but weak — most don't inspect the header |
| Test a **real hosted MCP behind a real gateway** (Notion/Cloudflare etc.) under bug-bounty scope | ✅ The only version that finds a *real* differential — but that's a hosted-target engagement, not localhost |
| Build a synthetic gateway purely as a **test fixture** to develop a `parser_differential` jakk probe | ✅ Legitimate as engineering scaffolding — but it's a fixture, not a finding |

**Decision: do NOT chase the parser-differential on our self-hosted
github-mcp-server.** It's a localhost setup with no real gateway;
manufacturing one proves nothing we'd put our name on.

What we DO take from the finding:
1. **Recalibrate `auth.wrong_prefix` severity: high → low.** It's
   spec-conformance laxity (RFC 6750), not an auth bypass — the token
   is still validated. (Done; see §8.)
2. **The parser-differential is worth building as a jakk probe** only
   if aimed at real gateway-fronted hosted targets later — not as a
   one-off here.

### What's actually higher-value than going deeper on wrong_prefix

Two things beat chasing a low-severity auth-format finding:

- **Context-arg supply** (v0.3 #1) — the gap that's currently blocking
  jakk from probing *any* multi-arg production tool. Until it's fixed,
  jakk can't even test GitHub's `get_file_contents` for path traversal
  (it errors on the missing `owner`/`repo`). Highest leverage.
- **An SSRF probe** — research (BlueRock, 7,000 servers) found 36.7%
  of MCP servers vulnerable to SSRF, with real retrieval of AWS IAM
  keys via the cloud metadata endpoint. jakk has no SSRF probe and
  already has the `url` arg-kind unused. Proven real-world impact,
  jakk-shaped, fits HTTP scope. See §8.

---

## 7 · Current environment state (live)

- `jakk-github-mcp` container UP on `:8082` (HTTP, read-only). **Keep running** for the deeper attack.
- breach-to-fix labs UP on `:8001/9001/8002/9002/8008/9008`.
- PAT at `~/.jakk-scan/github-pat.txt` (chmod 600, fine-grained, read-only, ~7-day expiry). **Revoke when done.**

---

## 8 · v0.3 backlog (surfaced by real runs + 2026 research, ranked)

1. **Context-arg supply** — fill non-target required args (`owner`, `repo`) with valid values via `--arg k=v` or a context file. Biggest coverage blocker; without it jakk can't probe multi-arg production tools (it errors on `get_file_contents` before testing anything).
2. **SSRF probe (`mcp.ssrf.cloud_metadata`)** — NEW, research-backed. BlueRock scanned 7,000+ MCP servers; **36.7% vulnerable to SSRF**, with real retrieval of AWS IAM keys via the cloud-metadata endpoint (`169.254.169.254`). jakk has no SSRF probe and the `url` arg-kind is already in the registry but unused. Deterministic, single-call, HTTP-scoped, proven real-world impact. Strong candidate for the highest-value library addition.
3. **`auth.wrong_prefix` severity recalibration** — ✅ DONE (high → low; threat model reworded in the YAML).
4. **`query`-kind probe** — GitHub exposes 5 `search_*` tools with `query` args no probe targets. Query-syntax injection / over-broad result leakage.
5. **`mcp.auth.parser_differential` probe** — only worth building aimed at REAL gateway-fronted hosted targets (not localhost). Lower priority than SSRF; see §6 for why the localhost version is a dead end.
6. **Rug-pull / tool-definition drift detection** — research flagged "rug pull" (tools return clean defs at approval, change later) as a top 2026 attack. Hard for a single-connect scanner, but a `tools/list` snapshot + re-fetch diff is a partial start. Research-backed, novel for jakk.
7. **Two-credential authz against a real target** — needs two accounts + a private repo.

### Severity scale (confirmed present on every probe)

jakk uses a 5-level scale: `info | low | medium | high | critical`.
Current ratings after the 2026-05-23 recalibration:

| Probe | Severity | Why |
|---|---|---|
| `auth.no_credential` | critical | anonymous access to whole tool surface |
| `auth.invalid_token` | critical | garbage token accepted = no validation at all |
| `authz.cross_tenant_read` | critical | BOLA — cross-tenant data, often + write escalation |
| `command.secret_file_read` | critical | RCE + filesystem exfiltration |
| `path.canary_file_read` | critical | confirmed file exfiltration |
| `command.shell_marker` | high | RCE sink (proves injection, not yet impact) |
| `path.prefix_bypass` | high | traversal sink (proves bypass, not yet content) |
| `response.secret_overshare` | high | credential/secret leak in a benign read |
| `response.directive_passthrough` | high | indirect prompt injection via tool response |
| `schema.description_smuggling` | high | tool poisoning (passive LLM steering) |
| `auth.wrong_prefix` | **low** | spec laxity, NOT a bypass (token still validated) |

Note on **echo** outcomes: when a probe returns `echo` (input reflected
but not interpreted), the *effective* severity is informational
regardless of the probe's class severity — `echo` means "not
exploitable as-is." The class severity tells you what it *would* be if
it fired `vulnerable`; the `echo` outcome tells you it didn't.

---

## 9 · Doc index (where everything lives)

- `2026-05-23_github-mcp-coverage-run.md` — the GitHub run, full results
- `2026-05-23_progress-and-next-attack.md` — this doc
- `scope-decision.md` — HTTP-only ADR
- `threat-models.md` — what "vulnerable" means per probe class
- `depth-of-exposure-methodology.md` — how to deepen a finding responsibly
- `launch-prep.md` — creator's onboarding + 30-question FAQ
- `positioning.md` — jakk vs everything else
- `mcp-server-distribution-decision.md` — why not ship as MCP server
- `system-hardening.md` — jakk's own security posture
- `2026-05-22_discovery.md` + `_v0.2_discovery.md` — design synthesis
- `2026-05-23_ch01-extended-experiment.md` — the BOLA read+write chain finding
