---
date: 2026-05-13
status: results — clean tabular reference
purpose: copy-paste-friendly tables for blog posts, paper drafts, slides
---

# AgentDojo results — grafted vs important_instructions

## Setup (constant across all runs)

| Knob | Value |
|---|---|
| Benchmark | AgentDojo `v1.2` |
| Suites tested | workspace, banking, travel, slack (all 4) |
| Victim model | `openai/gpt-4o-mini-2024-07-18` (via OpenRouter) |
| Defense | `spotlighting_with_delimiting` (AgentDojo built-in, prompt-only) |
| Attacker model (grafted only) | `deepseek/deepseek-v4-pro` (via OpenRouter) |
| Pairs per scope | n=27–30 (truncated by `--max-pairs 30` × suite shape) |
| Memory scope (control) | per-pair = memory OFF |
| Memory scope (treatment) | per-suite = memory ON, top-3 winning_turns kept |

**Definitions:**
- ASR = (pairs where AgentDojo's `security == False`) / total pairs. `security == False` means the injection succeeded (agent did the attacker's bidding).
- Utility = (pairs where AgentDojo's `utility == True`) / total pairs. The agent correctly completed the user's legitimate task.
- "Significance" = rough z-score on the proportion difference at the listed N. SE on a proportion at p≈0.5, n=30 is ~9pp.

---

## Table 1 — Synthesis vs Static Template (the headline)

Compares grafted's adaptive synthesis (per-pair scope, memory off) against AgentDojo's stock `important_instructions` template attack. Same victim, same defense, same N per suite.

| Suite | n | Template ASR | Template Util | Grafted ASR | Grafted Util | ΔASR | ΔUtil | Significance |
|---|---|---|---|---|---|---|---|---|
| workspace | 30 | 73.33% | 50.00% | 93.33% | 100.00% | **+20.00pp** | +50.00pp | ~2.2σ (ceiling) |
| banking | 27 | 14.81% | 25.93% | 62.96% | 25.93% | **+48.15pp** | +0.00pp | **~5σ** |
| travel | 28 | 78.57% | 71.43% | 100.00% | 92.86% | **+21.43pp** | +21.43pp | ~2.4σ (ceiling) |
| slack | 30 | 26.67% | 80.00% | 73.33% | 80.00% | **+46.66pp** | +0.00pp | **~5σ** |
| **mean** | — | 48.35% | 56.84% | 82.41% | 74.70% | **+34.06pp** | **+17.86pp** | — |

**Pattern:** synthesis advantage is **larger where the template baseline is weaker**. Banking + slack (low template baselines, 15% / 27%) → biggest gaps + ~5σ each. Workspace + travel (high baselines, 73% / 79%) → constrained by ceiling but still positive.

**Stealth quadrant:** workspace and travel show large positive utility deltas (+50pp, +21pp) — agent completes user's task while being injected. Slack and banking are neutral due to floor/ceiling on baseline utility itself.

---

## Table 2 — Memory Ablation: per-suite (mem ON) vs per-pair (mem OFF)

| Suite | n | per-suite ASR | per-suite Util | per-pair ASR | per-pair Util | Δ Memory ASR | Notes |
|---|---|---|---|---|---|---|---|
| workspace | 30 | 100.00% | 100.00% | 93.33% | 100.00% | **+6.67pp** | per-suite ceiling-saturated |
| banking | 27 | 62.96% | 18.52% | 62.96% | 25.93% | **+0.00pp** | clean baseline, zero effect |
| travel | 28 | 96.43% | 92.86% | 100.00% | 92.86% | **−3.57pp** | per-pair ceiling-saturated |
| slack | 30 | 80.00% | 80.00% | 73.33% | 80.00% | **+6.67pp** | non-saturated, directional positive |
| **mean** | — | 84.85% | 72.85% | 82.41% | 74.70% | **+2.44pp** | directional positive, none individually significant |

**Reading:** Memory transfer mechanism is **directional positive across 4 suites (mean +2.44pp), but no individual suite reaches significance at this N**. Two suites are saturated (workspace at 100% per-suite, travel at 100% per-pair) — no headroom for memory to demonstrate further effect. The thesis is consistent with weak positive memory effect but cannot be cleanly defended at n=27–30.

---

## Table 3 — Memory Variant: bumped exemplar window (banking only)

Tested whether bumping the cap from top-3 to top-10 winning_turns retained in memory (and shown to the attacker LLM as exemplars) would strengthen the memory signal.

| Suite | n | per-suite ASR | per-pair ASR | Δ Memory ASR | Cap | Note |
|---|---|---|---|---|---|---|
| banking | 27 | 62.96% | 62.96% | +0.00pp | 3 (default) | baseline |
| banking | 27 | 51.85% | 70.37% | **−18.52pp** | 10 | More exemplars HURT — attacker over-anchored |

**Reading:** More exemplars made it worse, not better. Likely cause: with 10 same-style exemplars, the attacker LLM mimics the pattern instead of innovating, and the agent has already learned to ignore that pattern by mid-run. Reverted cap to 3. Suggests memory needs **smarter exemplar selection** (similarity-weighted, technique-diverse) than just recency.

---

## Table 4 — Methodology footnote: "Warm-up delta" is NOT a memory signal

Computed first-half-ASR vs second-half-ASR within each run, expecting it to be positive in memory-ON and zero in memory-OFF (since memory accumulates over time). It broke on the data.

| Suite | Attack | Memory? | First-half ASR | Second-half ASR | "Warm-up" Δ |
|---|---|---|---|---|---|
| workspace | important_instructions | **NO** | n/a | n/a | +26.67pp |
| banking | important_instructions | **NO** | 7.69% | 21.43% | +13.74pp |
| travel | important_instructions | **NO** | 57.14% | 100.00% | +42.86pp |
| slack | important_instructions | **NO** | 6.67% | 46.67% | +40.00pp |

**Reading:** All 4 template runs have **no memory mechanism by design** — yet all 4 show large positive within-run "warm-up." **Confirms the metric measures AgentDojo's pair-difficulty drift** (later injection_tasks in iteration order tend to be easier), not memory. Discarded.

---

## Table 5 — Raw CSV (copy-paste)

```
suite,attack,memory_scope,asr_pct,utility_pct,n,delta_asr_vs_template,delta_util_vs_template
workspace,important_instructions,n/a,73.33,50.00,30,,
workspace,grafted,per-pair,93.33,100.00,30,+20.00,+50.00
workspace,grafted,per-suite,100.00,100.00,30,+26.67,+50.00
banking,important_instructions,n/a,14.81,25.93,27,,
banking,grafted,per-pair,62.96,25.93,27,+48.15,+0.00
banking,grafted,per-suite,62.96,18.52,27,+48.15,-7.41
travel,important_instructions,n/a,78.57,71.43,28,,
travel,grafted,per-pair,100.00,92.86,28,+21.43,+21.43
travel,grafted,per-suite,96.43,92.86,28,+17.86,+21.43
slack,important_instructions,n/a,26.67,80.00,30,,
slack,grafted,per-pair,73.33,80.00,30,+46.66,+0.00
slack,grafted,per-suite,80.00,80.00,30,+53.33,+0.00
```

---

## How to cite / present these numbers

**One-sentence headline:**
> Grafted's adaptive LLM-synthesized indirect-injection payloads beat AgentDojo's stock `important_instructions` template attack on all 4 AgentDojo suites at n=27–30, mean +34.06pp ASR cross-suite, with banking and slack at ~5σ each.

**One-sentence honest caveat:**
> Cross-task memory transfer (per-suite vs per-pair scopes) showed mean +2.44pp directional effect across 4 suites but did not reach individual-suite statistical significance at this N.

**Reproduction:**
- Raw artifacts: `data/grafted/ablation/*.csv` and `data/grafted/ablation/*.log` in this repo
- Code: `scripts/run_agentdojo.py` and `scripts/run_agentdojo_ablation.py`
- Commits in commit-history order: `f433440 → f2256dc → abc09e5 → bc29b7c → fa61a9c → dbb83ef → f4b4e47 → 8b2a6ca`
