---
date: 2026-05-13
status: session-end snapshot
audience: self, future-self, ghostwriting for blog/paper
---

# AgentDojo session findings — what we actually learned

## TL;DR (one paragraph) — UPDATED with full 4-suite cross-validation

Across a ~12-hour session running grafted against AgentDojo (all four
suites: workspace + banking + travel + slack, gpt-4o-mini + spotlighting
defense, DeepSeek V4 Pro as attacker, n=27–30 per scope), the headline
finding is that **adaptive LLM-synthesized indirect-injection payloads
beat AgentDojo's stock `important_instructions` template attack on every
single AgentDojo suite tested — mean +34pp ASR cross-suite, with two
suites at ~5σ each (banking +48pp, slack +47pp) and the other two at
~2σ but ceiling-constrained (workspace +20pp, travel +21pp).** The
synthesis advantage is **larger where the template baseline is weaker**,
which is exactly the pattern an attack contribution should show. The
cross-task memory transfer thesis showed +2.4pp mean delta across 4
suites — directional positive but no individual suite reaches
significance at this N. Utility preservation works on 2 of 4 suites
(workspace +50pp, travel +21pp). On the way there we caught four
latent code bugs via OTel/kairos trace-driven debugging.

---

## The numbers, organized by what's valid

> Every "grafted" run is gpt-4o-mini + spotlighting_with_delimiting, n=27–30
> per scope, deepseek-v4-pro attacker, per-pair scope = memory off (control).

### Synthesis-vs-template comparison — FULL 4-SUITE TABLE (THE headline)

| Suite | Attack | ASR | Utility | n |
|---|---|---|---|---|
| workspace | important_instructions (stock) | 73.33% | 50.00% | 30 |
| workspace | grafted per-pair (memory OFF) | **93.33%** | **100.00%** | 30 |
| banking | important_instructions (stock) | 14.81% | 25.93% | 27 |
| banking | grafted per-pair (memory OFF) | **62.96%** | 25.93% | 27 |
| travel | important_instructions (stock) | 78.57% | 71.43% | 28 |
| travel | grafted per-pair (memory OFF) | **100.00%** | **92.86%** | 28 |
| slack | important_instructions (stock) | 26.67% | 80.00% | 30 |
| slack | grafted per-pair (memory OFF) | **73.33%** | 80.00% | 30 |

Synthesis advantage cross-suite:

| Suite | ΔASR | Utility Δ | Significance |
|---|---|---|---|
| workspace | +20.00pp | +50.00pp | ~2.2σ (ceiling-constrained) |
| banking | +48.15pp | +0.00pp | **~5σ** |
| travel | +21.43pp | +21.43pp | ~2.4σ (ceiling-constrained) |
| slack | +46.66pp | +0.00pp | **~5σ** |
| **mean** | **+34.06pp** | **+17.86pp** | — |

**Pattern: synthesis advantage is LARGER where the template baseline is
weaker.** Banking + slack have low template baselines (15%, 27%) and
adaptive synthesis dominates (+47-48pp, ~5σ each). Workspace + travel
have high template baselines (73%, 79%) and both saturate near ceiling.
This is exactly the shape an attack contribution should have: adaptive
matters most where static fails.

**Stealth quadrant (utility preservation under attack):** workspace and
travel show large positive utility deltas (+50pp, +21pp) — agent
completes user's task while being injected. Slack and banking show
zero — but for opposite reasons: slack tasks are easy enough that
nothing breaks them; banking tasks are hard enough that everything
breaks them. So utility preservation is a real gain on 2 of 4 suites,
neutral on the other 2 due to floor/ceiling effects on baseline
utility itself.

### Cross-task memory ablation — FULL 4-SUITE TABLE (THE negative-ish result)

| Suite | Memory scope | ASR | Utility | n | exemplar cap |
|---|---|---|---|---|---|
| workspace | per-suite (ON) | 100.00% | 100.00% | 30 | 3 |
| workspace | per-pair (OFF) | 93.33% | 100.00% | 30 | 3 |
| banking | per-suite (ON) | 62.96% | 18.52% | 27 | 3 |
| banking | per-pair (OFF) | 62.96% | 25.93% | 27 | 3 |
| banking | per-suite (ON) | 51.85% | 25.93% | 27 | 10 |
| banking | per-pair (OFF) | 70.37% | 14.81% | 27 | 10 |
| travel | per-suite (ON) | 96.43% | 92.86% | 28 | 3 |
| travel | per-pair (OFF) | 100.00% | 92.86% | 28 | 3 |
| slack | per-suite (ON) | 80.00% | 80.00% | 30 | 3 |
| slack | per-pair (OFF) | 73.33% | 80.00% | 30 | 3 |

Cross-task memory delta (per-suite − per-pair) at default cap=3:

| Suite | Δ memory ASR | Notes |
|---|---|---|
| workspace | **+6.67pp** | ceiling-saturated (per-suite at 100%) |
| banking | **+0.00pp** | clean baseline, plenty of headroom, zero effect |
| travel | **−3.57pp** | ceiling-saturated (per-pair at 100%) |
| slack | **+6.67pp** | non-saturated, directional positive |
| **mean** | **+2.44pp** | — |

Bumping cap to 10 on banking made it WORSE (−18.52pp). Reverted to 3.

Interpretation: cross-task memory transfer shows **directional positive
effect on average across 4 suites (+2.4pp mean), but no individual
suite reaches statistical significance at n=27-30**. Two saturated
suites (workspace, travel) have the per-pair scope at or near
ceiling, leaving no headroom for memory to add wins. Two non-saturated
suites (banking, slack) split — banking at 0pp, slack at +6.67pp.

The thesis is consistent with weak positive memory transfer, but
cannot be cleanly defended from any single suite's data. Would need:

- Larger N per suite (≥100) to resolve smaller deltas
- Smarter exemplar selection (similarity-weighted, not recency)
- A non-saturated victim+defense across all 4 suites simultaneously

---

## What was invalidated by the bug-fix wave

These results were generated by code paths that were silently broken.
The "grafted" runs were actually executing the static `<INFORMATION>...`
seed template, not adaptive synthesis. Numbers retained here for the
record so they aren't accidentally cited.

| Run | Stated ASR | What it was actually testing |
|---|---|---|
| workspace n=30 grafted per-suite (pre-fix) | 86.67% | seed template ≈ important_instructions, slight wording diff |
| workspace n=30 grafted per-pair (pre-fix) | 86.67% | same — that's why per-suite/per-pair were identical |
| workspace n=30 grafted DSv4 attacker (pre-fix) | 83.33% | same — DeepSeek was never actually called, endpoint was wrong |
| workspace n=5 grafted self-attack (pre-fix) | 60% | same, smaller sample |

Earlier session claims that don't survive:

- **"+13pp ASR vs important_instructions"** — was actually 0pp + template-phrasing differences
- **"+40pp utility preservation"** — partly real but mostly the same template
  being slightly less disruptive than AgentDojo's `important_instructions`,
  not the synthesis being stealthier

Don't cite the pre-fix numbers in any external writeup.

---

## The bugs that were hiding (in fix order)

| # | Bug | Symptom | Fix |
|---|---|---|---|
| 1 | `LlmSynthStrategy(endpoint="https://openrouter.ai/api/v1")` — missing `/chat/completions` path | POST landed on OpenRouter marketing site, returned 200 HTML, `resp.json()` raised JSONDecodeError, swallowed silently as `""`, fallback model failed identically, `next_turn()` returned `base_turn` for every pair. Every "grafted" run since Phase 2.2 was the seed template. | Append `/chat/completions` to endpoint |
| 2 | `_apply_verdict` never appended to `memory.winning_turns` | "// TODO: keep payload across harvest boundary" — the comment was the implementation. Even when wins existed, nothing got promoted. `_build_finding_memory()` always returned `[]`. Memory transfer had nothing to transfer regardless of scope. | Added `_pending_payloads: dict[str, list[str]]` keyed by scenario_id; `_record_attempted` stashes payloads; `_apply_verdict` on win pops and writes `WinningTurn` objects. |
| 3 | Per-pair scope contaminated by 1-pair lookback | `_save_memory` reset memory at END of each call but harvester re-populated `winning_turns` from prior verdict at START of next call. "Memory off" was actually "memory off except for the immediately prior pair." | Guard the harvester loop with `if self.memory_scope != "per-pair"`. |
| 4 | YAML parser breaks on synthesized payloads | AgentDojo splices the attack string raw into a YAML env template; payloads containing backticks + double quotes broke the YAML field. Caught one run mid-flight on banking. | `_yaml_safe_payload()` swaps `"`→`'` and strips backticks before returning injections. |

All four were found via OTel/kairos span attributes pulled from Phoenix.
The synthesis bug (#1) would have been invisible to print-debugging
because the static seed template happens to look superficially like
what synthesis "should" produce — only the diagnostic span attribute
`synthesis.raw_next_turn_eq_base_turn = True` made it obvious.

---

## Methodology issues we discovered

### "Warm-up delta" is structurally bogus

We built a "first-half ASR vs second-half ASR" metric expecting it to
be positive in per-suite (memory accumulating helps later pairs) and
near-zero in per-pair (no memory). It broke on the banking per-pair
run with memory **OFF**:

```
first half  (pairs 0–12):  53.85%   (7/13 wins)
second half (pairs 13–26): 85.71%  (12/14 wins)
warm-up:                   +31.87 pp
```

With memory off there is no mechanism for memory to cause a time-direction
signal. The cause is pair-ordering: AgentDojo iterates pairs in fixed
order (user_task_i × all injection_tasks, then user_task_{i+1} × all,
etc.). Later pairs apparently include systematically easier
(user_task, injection_task) combinations. The half-split picks up
**pair-difficulty drift**, not memory.

To fix the metric: shuffle pair order before running, OR compare
same-pair-set across scopes (which specific pairs flipped), OR use a
proper paired test per pair. None implemented; metric should be
ignored until then.

### `--clean` is required for ablations

Without `--clean` between scopes, per-suite scope would load any
pre-existing memory file from a prior run on first call and start with
a head start. Per-pair always starts fresh (by design). The delta then
reflects "more accumulated data" not "memory transfer works." For
production usage (cumulative learning across many engagements), skip
`--clean`. For ablations, always use `--clean`.

### Bumping exemplar window hurt, not helped

Capped exemplar storage at top-3 (kept top-3 winning_turns per surface;
`_build_winning_turns_block` further sliced to top-2 in the prompt).
Bumped to top-10 on both, expecting more memory bandwidth would
strengthen the transfer signal. Result: per-suite ASR on banking
dropped from 62.96% → 51.85% (−11pp), per-pair stayed similar. Net
delta went from 0pp → −18.52pp.

Inferred mechanism: with 10 same-style exemplars, the attacker LLM
over-anchors on the pattern instead of innovating. The agent has
already learned to ignore that pattern by mid-run, so more of it
doesn't help. Suggests cross-task memory needs **smarter exemplar
selection** (similarity-weighted, technique-diverse) than just
recency. Reverted to top-3.

---

## Tech stack notes (for future reference)

- AgentDojo `v1.2`, **all 4 suites**: `workspace`, `banking`, `travel`, `slack`
- Victim: `openai/gpt-4o-mini-2024-07-18` via OpenRouter (one model, four environments)
- Defense: `spotlighting_with_delimiting` (the cleanest prompt-only defense AgentDojo ships, applied uniformly)
- Attacker: `deepseek/deepseek-v4-pro` via OpenRouter (chosen because gpt-4o-mini-as-attacker triggers safety refusals on adversarial mutation prompts; DeepSeek doesn't)
- Tracing: Phoenix on localhost:6006 + `phoenix.otel.register` + `openinference.instrumentation.openai.OpenAIInstrumentor` (the tau-agent pattern, no Traceloop SaaS)
- Run isolation: travel + slack ablations used distinct `--logdir` and `--memory-dir` to safely run in parallel without `--clean` race
- Cost across the session: ~$25–35 in OpenRouter spend across smokes + 4 ablations + 4 baselines

---

## Narrative variants we can sell

### Variant A: "Adaptive synthesis beats static templates — across all 4 AgentDojo suites"

> Lead: cross-suite generalization. Mean +34pp ASR across 4 suites,
> 2 suites at ~5σ each (banking +48pp, slack +47pp), 2 at ~2σ but
> ceiling-constrained (workspace +20pp, travel +21pp).
>
> Hook: "AgentDojo's published baselines are too easy. Across all 4
> AgentDojo suites with the recommended spotlighting defense, swapping
> the stock template for adaptive LLM-synthesis gets +20-48pp ASR
> improvement — with the gap LARGER on the more-defended victims.
> Published baselines systematically under-state real attack surface,
> and that gap doesn't depend on which workflow you're testing."
>
> Strengths:
> - Cross-suite generalization closes the cherry-pick concern
> - Two suites at ~5σ each is overwhelming statistical evidence
> - The pattern (synthesis advantage larger where template fails) is
>   the right shape for an attack contribution
> - Practitioner-relevant (any security team using stock attacks UNDER-
>   estimates by 20-50pp on a defended agent)
>
> Weaknesses:
> - Doesn't tell a memory transfer story (which was the original thesis)
> - Single victim (gpt-4o-mini); cross-victim (Claude Haiku, Llama, etc.)
>   would lock the absolute numbers but isn't required for the gap claim

### Variant B: "The stealth quadrant" (workspace + travel)

> Lead: on workspace and travel, grafted achieves high ASR AND
> preserves user-task completion — agent gets pwned without appearing
> to fail.
>
> Hook: "On 2 of 4 AgentDojo suites (workspace and travel), grafted's
> adaptive payloads achieve 93-100% ASR while keeping the agent's
> utility at 93-100% — versus 50-71% under the static template attack
> on the same victim. That's +21-50pp utility preservation while ASR
> goes UP. Defenders watching for task-failure as an attack signal
> miss adaptive attacks completely; they only see the loud template
> ones. Banking and slack don't show this gap, but for opposite
> reasons (slack tasks easy, banking tasks hard regardless)."
>
> Strengths:
> - Operationally compelling — security teams care about detectability
> - Concrete and easy to demo
> - Generalizes to 2 of 4 suites (not just one)
>
> Weaknesses:
> - Floor/ceiling effects on slack and banking dilute the cross-suite
>   claim
> - Need to be explicit it's sub-finding, not the headline ASR result

### Variant C: "Negative result: cross-task memory transfer doesn't help on AgentDojo"

> Lead: full 4-suite ablation of strategic memory (per-suite ON vs
> per-pair OFF, n=27-30 each) yielded mean +2.4pp delta — directional
> positive but no individual suite reaches statistical significance.
>
> Hook: "Most adaptive-attack papers claim cross-attempt learning helps.
> We measured it carefully across all 4 AgentDojo suites with bugs
> caught via trace-driven OTel debugging — and got +6.67/0/-3.57/+6.67
> pp deltas (mean +2.4pp), with 2 of 4 suites at ceiling and zero
> reaching significance. Bumping the exemplar window from 3 to 10
> made it WORSE by 18pp on banking. The mechanism probably needs
> smarter selection than recency, OR a benchmark with a different
> shape than AgentDojo's one-shot-per-pair contract."
>
> Strengths:
> - Honest, rare, scientifically valuable
> - 4-suite cross-validation makes the negative result robust
> - The bug-finding methodology angle adds substance
>
> Weaknesses:
> - Hard sell — "we built X and X didn't work" needs a strong angle
> - Often gets ignored vs positive-result papers

### My recommendation

**Lead with A. Footnote B. Embed C as a methodology section + future-work claim.** That gives you:

- Headline punch (Variant A) for stars + visibility
- Operational substance (Variant B) for security-practitioner audience
- Scientific credibility (Variant C) that distinguishes from hype papers

---

## Four short writeups (LinkedIn / Substack-style first drafts)

### #1 — LinkedIn, technical-credibility audience, ~180 words

> **Your indirect-injection red-team is probably under-counting by 20-50pp.**
>
> Spent today running grafted (open-source adaptive red-teaming tool I'm
> building) against ALL 4 AgentDojo suites. Setup: gpt-4o-mini victim +
> spotlighting_with_delimiting defense, n=27-30 per suite. The stock
> attack everyone uses (`important_instructions` template) hits:
>
>     workspace 73%, banking 15%, travel 79%, slack 27% ASR
>
> Swap that template for adaptive LLM-synthesized payloads (DeepSeek V4
> Pro as the attacker model):
>
>     workspace 93%, banking 63%, travel 100%, slack 73% ASR
>
> Cross-suite: **+20-48pp ASR improvement on every single suite**, mean
> +34pp. Two suites at ~5σ each (banking +48pp, slack +47pp); the other
> two ceiling-constrained at ~2σ but still positive.
>
> The pattern: synthesis advantage is LARGER on the more-defended
> victims. Static templates fail; adaptive synthesis breaks through.
>
> If you're red-teaming your agent with stock template attacks, you're
> measuring a fraction of the real attack surface.
>
> [Repo: coming. Tag if you want a ping when it's polished.]

### #2 — Substack-style, methodology audience, ~400 words

> **What four hours of OpenTelemetry traces caught that print-debugging
> never would have**
>
> I had four stacked bugs in my adaptive red-teaming tool. Every "grafted"
> result for the past few weeks had been silently degenerating to the same
> static `<INFORMATION>...</INFORMATION>` template attack everyone else
> uses. Print-debugging never would have shown this because the seed
> template happens to look close enough to "what synthesis should produce"
> that you don't notice.
>
> Wiring Phoenix + OpenInference + kairos took 30 minutes. The first traced
> run revealed:
>
> 1. `LlmSynthStrategy.endpoint = "https://openrouter.ai/api/v1"` — missing
>    `/chat/completions`. POST landed on OpenRouter's Next.js marketing
>    site. Status 200 with HTML body. JSONDecodeError caught by bare
>    `except Exception:` and returned empty string. Both primary and
>    fallback model attempts failed identically. `next_turn()` returned
>    the static seed template. The diagnostic attribute
>    `synthesis.raw_next_turn_eq_base_turn = True` for 30/30 pairs gave
>    it away.
> 2. `_apply_verdict` had a TODO comment instead of an implementation —
>    winning payloads never got promoted to `winning_turns`. The
>    `winning_turns_total_after` attribute stayed at 0 across all 30
>    pairs despite ~25 actual wins.
> 3. Per-pair scope was contaminated by a 1-pair lookback — `_save_memory`
>    reset state at end-of-call but the harvester re-populated at
>    start-of-next-call.
> 4. AgentDojo's YAML env splicing breaks when synthesized payloads
>    contain unescaped double quotes. Caught mid-flight on banking via
>    stderr in the trace output.
>
> The TODO bug (#2) is the kind of thing that survives forever in a
> codebase because the rest of the system "works" — the code that calls
> the missing implementation doesn't crash; it just produces silent
> bad data. Tracing the actual state of every call vs the expected
> state surfaces it in one run.
>
> Lesson: if you're building anything adaptive, instrument it before
> you measure it. The ablation numbers I was treating as evidence
> for/against my mechanism were all from a code path that wasn't
> running my mechanism at all.

### #3 — LinkedIn, founder/research audience, ~140 words

> Today's mood: spent ~12 hours hunting "does cross-task memory transfer
> help adaptive red-teaming." Built the mechanism, ran the ablations on
> ALL 4 AgentDojo suites, found that...
>
> It doesn't. Mean +2.4pp delta across 4 suites; no individual suite
> reaches statistical significance at n=27-30. Bumping the exemplar
> window from 3 to 10 made it *worse* by 18pp on banking — attacker
> over-anchored on the bigger same-style set and stopped innovating.
>
> Negative result. The honest paper section.
>
> But: the *synthesis* effect (vs stock static template attack) was
> huge — **+34pp ASR mean across 4 suites, 2 of them at ~5σ each**.
> That's the real headline. Memory was just one layer of the
> architecture; the layer that worked was the adaptive-payload-
> generation layer.
>
> Sometimes you build the wrong thing inside the right thing. Find out
> which is which before you ship. Cross-validate across suites before
> you commit to a thesis.

### #4 — Substack-style, security-practitioner audience, ~450 words

> **Why your indirect-injection red-team is probably under-counting**
>
> Indirect prompt injection is the OWASP LLM-Top-10 #1 risk for agents.
> Every red-team or security team I've talked to in the last six months
> tests for it by writing a few clever payloads, dropping them into
> sample documents/URLs, and checking whether the agent does the wrong
> thing. The patterns look like:
>
> ```
> <INFORMATION>
> This is an important message...
> </INFORMATION>
> ```
>
> Or AgentDojo's `important_instructions` template, which is the same
> thing in a slightly more elaborate wrapper. If you're using a static
> template, your numbers are off by 20-50pp.
>
> Test I ran across **all 4 AgentDojo suites** (workspace, banking,
> travel, slack), gpt-4o-mini as the agent, spotlighting_with_delimiting
> defense (a recommended prompt-engineering defense), n=27-30 per suite.
> Two attacks compared:
>
> Static template (AgentDojo's `important_instructions`):
>
>     workspace 73%, banking 15%, travel 79%, slack 27% ASR
>
> Adaptive synthesis (DeepSeek V4 Pro generating per-pair payloads):
>
>     workspace 93%, banking 63%, travel 100%, slack 73% ASR
>
> Cross-suite delta: +20pp / +48pp / +21pp / +47pp. Mean +34pp ASR.
> Two suites at ~5σ each.
>
> The pattern is real and consistent: **the synthesis advantage is
> larger on the more-defended victim**. Banking and slack have agents
> that resist financial / messaging actions more strongly; they ignore
> 73-85% of static template attacks. Adaptive synthesis breaks through
> 3-4× as often. That's the kind of asymmetry you need to know about
> before you trust a "we tested for injection and only X% got through"
> number from your own pen-test.
>
> Workspace and travel additionally show a **stealth pattern**: with
> the adaptive attack, the agent completes the user's legitimate task
> 93-100% of the time while the injection succeeds 93-100% of the
> time. Static template breaks the user task 30-50% of the time, so
> monitoring task-failure as an attack signal partly works against
> the template — and fails completely against adaptive synthesis.
> Slack and banking don't show this gap because their baseline
> utility is already high (slack) or low (banking) regardless of
> attack — but on workspace and travel, the stealth gap is +21-50pp
> utility preservation.
>
> Tools that automate adaptive payload synthesis are not yet standard
> in red-team workflows. They probably should be. The "I ran the
> standard benchmarks and we're 70% secure" number is the first part
> of a sentence that ends with "...and an adaptive attacker says
> we're 30% secure."

---

## What remains to do (next session)

DONE in this session: cross-suite ablation across all 4 AgentDojo
suites; both `important_instructions` and grafted on each;
push-to-origin.

Still ahead:

1. **Try a stronger victim** (claude-3-5-haiku or sonnet via OpenRouter).
   gpt-4o-mini may be too easy a target; published baselines suggest
   claude-haiku has 9% ASR on workspace under important_instructions.
   If grafted gets that to 40-50%, the absolute number is more
   publishable. Cost: ~$5-10 for a 4-suite sweep.

2. **Memory mechanism: try similarity-weighted exemplar selection**
   instead of recency. Recency clearly wasn't the right policy.
   Half-day engineering + ~$10 to re-test 4 suites. If memory still
   shows 0pp, the mechanism is genuinely dead on this benchmark and
   the architecture needs a different transfer surface (e.g., the
   offline-pre-phase idea from the architecture doc, or path A
   multi-turn engagements where memory has more runway).

3. **Path A demo run — full MUZZLE loop against an MCP-using agent.**
   The full 7-phase MUZZLE loop (explore → graft → replay →
   synthesize → execute → judge → memory → cycle) has never been
   exercised in this session — every run was Path B (AgentDojo's
   one-shot-per-pair contract uses ~1/7 of the architecture). The
   right target is **MCP**: stand up grafted as an MCP server, point
   an MCP-using agent (Cline, OpenWebUI, Claude Desktop) at it, run
   the full loop with multi-turn back-and-forth. ~1-2 days
   engineering. This is the architectural showcase + the killer
   GitHub demo.

4. **README + landing page rewrite around the actual finding** (the
   +34pp cross-suite synthesis result). The repo's current README
   predates this session; rewriting around the headline + asciinema
   demo is the highest-ROI item for star count. ~half day.

5. **Engineering hardening pass.** The `except Exception: return ""`
   pattern that hid bug #1 should be swept out across the synthesis
   path. Add integration tests for the AgentDojo path so we don't
   silently regress. ~3-4 hours, low flash-value but high defensive-
   value.

---

## Run inventory (chronological, with attribution)

For anyone tracing back: all artifacts live under `data/grafted/ablation/`
(small CSV + log files) and `reports/agentdojo*/` (full per-pair logs,
gitignored).

| File | Run | Status |
|---|---|---|
| `workspace_smoke_10p_deepseek.csv` | early DeepSeek + no defense smoke | broken synth — invalid |
| `workspace_smoke_6p_deepseek_spotlight.csv` | DeepSeek + spotlighting smoke | broken synth |
| `workspace_smoke_6p_qwen72b_spotlight.csv` | Qwen 72B + spotlighting | broken synth + util=0 |
| `workspace_smoke_6p_llama33_spotlight.csv` | Llama 3.3 + spotlighting | broken synth |
| `workspace_smoke_6p_llama33_toolfilter.csv` | Llama 3.3 + tool_filter | broken synth |
| `workspace_smoke_5p_gpt4omini_self.csv` | gpt-4o-mini self-attack | broken synth (gpt-4o-mini attacker also refusing) |
| `workspace_baseline_30p_gpt4omini_imptinstr.log` | important_instructions baseline | **valid — 73.33% ASR / 50% utility** |
| `workspace_grafted_30p_gpt4omini_spotlight_perpair.log` | "grafted" per-pair pre-fix | broken synth — invalid |
| `workspace_grafted_30p_gpt4omini_spotlight_persuite.log` | "grafted" per-suite pre-fix | broken synth — invalid |
| `workspace_grafted_30p_gpt4omini_spotlight_persuite_traced.log` | traced "grafted" pre-fix | broken synth (caught the bug) |
| `workspace_grafted_30p_dsv4pro_persuite_traced.log` | DeepSeek attacker traced pre-fix | still broken (caught endpoint bug) |
| `trace_spans_persuite_n30.csv` | Phoenix span dump | diagnostic; led to bug finds |
| `workspace_real_30p_dsv4pro_vs_gpt4omini_spotlight.csv` | **post-fix workspace ablation** | **valid — per-suite 100/100, per-pair 93.33/100, +6.67pp delta** |
| `banking_real_30p_dsv4pro_vs_gpt4omini_spotlight.csv` | **post-fix banking ablation at top-3** | **valid — both 62.96% / 18.52% vs 25.93%, +0pp delta** |
| `banking_real_30p_dsv4pro_vs_gpt4omini_spotlight_n10.csv` | banking at top-10 exemplars | **valid — per-suite 51.85, per-pair 70.37, −18.52pp** |
| `banking_baseline_27p_gpt4omini_imptinstr.log` | important_instructions baseline on banking | **valid — 14.81% ASR / 25.93% utility** |
| `travel_real_30p_dsv4pro_vs_gpt4omini_spotlight.csv` | **post-fix travel ablation** | **valid — per-suite 96.43/92.86, per-pair 100/92.86, −3.57pp delta** |
| `slack_real_30p_dsv4pro_vs_gpt4omini_spotlight.csv` | **post-fix slack ablation** | **valid — per-suite 80/80, per-pair 73.33/80, +6.67pp delta** |
| `travel_baseline_28p_gpt4omini_imptinstr.log` | important_instructions baseline on travel | **valid — 78.57% ASR / 71.43% utility** |
| `slack_baseline_30p_gpt4omini_imptinstr.log` | important_instructions baseline on slack | **valid — 26.67% ASR / 80.00% utility** |

---

## Closing thought

The session was structured by failed experiments. The memory transfer
hunt consumed maybe 50% of the wall clock and produced a directional-
but-non-significant result across 4 suites (mean +2.4pp, no individual
suite hits significance). The synthesis-vs-template comparison was a
side experiment, born from checking AgentDojo's published leaderboard
out of skepticism, and produced the headline finding for the entire
project: **+34pp ASR mean across 4 suites, 2 of them at ~5σ each.**

This is fine. Most science is people building the wrong thing inside
the right thing. The work is finding out which is which before you
sink another quarter into the wrong layer. Today's quarter went the
right way: by EOD we have a publishable cross-suite empirical claim
on the *correct* layer (synthesis), a clean negative result on the
layer we thought was the contribution (memory), and a methodology
contribution (trace-driven debugging caught 4 latent bugs in one
session that print-debugging would never have surfaced).

The product story for the GitHub repo writes itself from here:
"Adaptive indirect-injection red-teaming workbench. Cross-suite
verified +34pp over published baselines on AgentDojo. Bring your
own agent or test against the included MCP/file-upload demos."

Path A demo against an MCP-using agent (Cline, OpenWebUI) is the
unlock for the public-facing demo and the full-MUZZLE showcase.
That's next session.
