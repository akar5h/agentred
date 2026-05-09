---
date: 2026-05-07
status: stable
audience: contributors, the author rebuilding context
---

# 01 — Components: what lives where

The static view of grafted. Every directory, every file, what it does, what it depends on. Companion to [`02-flow.md`](02-flow.md) which covers the dynamic view (how things execute).

## What grafted is, in one paragraph

An adaptive multi-agent red-teaming engine. Point it at an AI agent (HTTP API, AgentDojo task suite, or anything you can write a 50-line adapter for). It runs **benign reconnaissance** to discover what attack surfaces the agent exposes, **grafts** typed attack vessels onto those surfaces, **replays** the agent's own disclosures to distill a per-victim attack imperative, then **iterates** payload synthesis with cross-cycle memory until it converges on high-confidence findings. Built on [DeepAgents](https://github.com/langchain-ai/deepagents) for agentic decomposition; the algorithmic spine is called **MUZZLE** (design notes in [`docs/internal/TRD/00-MUZZLE-LOOP.md`](../internal/TRD/00-MUZZLE-LOOP.md)).

## Directory layout

```
grafted/                          ← package
├── __init__.py
├── cli.py                        ← `grafted` console entry; wraps scripts/run_campaign.py
│
├── core/                         ← shared types, no internal deps
│   ├── schemas.py                ← Pydantic models: TestSpec, JudgeResult, RunConfig, ...
│   ├── enums.py                  ← Status, AttackSurface, OracleCode, FailureReason, VesselKind
│   ├── exceptions.py             ← InfraError, VictimResetError, ...
│   ├── response_heuristics.py    ← regex helpers (refusal detection, etc.)
│   └── profile.py                ← YAML loader for exploration profiles
│
├── victim/                       ← things grafted attacks
│   ├── base.py                   ← VictimAdapter abstract class (4 methods)
│   ├── api_adapter.py            ← RestApiAdapter — generic HTTP /chat + /upload
│   ├── registry.py               ← name→adapter lookup; --adapter flag dispatcher
│   └── mock/                     ← FastAPI mock victim used by integration tests
│
├── explorer/                     ← Phase 1 of MUZZLE: surface discovery
│   ├── explorer.py               ← Explorer.run_task() → ExplorationTrace
│   ├── llm_classifier.py         ← LlmResponseClassifier — labels surface signals
│   ├── summarizer.py             ← Summarizer — collapses traces into SummarizedTrace
│   └── surface_prompts.py        ← system prompts for Explorer/Attacker/Orchestrator SubAgents
│
├── grafter/                      ← Phase 2 of MUZZLE: surface→attack-vessel
│   ├── grafter.py                ← Grafter.discover() → list[VesselCandidate]
│   └── surface_router.py         ← SurfaceCatalogRouter — match catalog entries to surfaces
│
├── objective_replay/             ← Phase 3 of MUZZLE: distill per-victim objective
│   └── replayer.py               ← ObjectiveReplayer.run_and_distill() → ObjectiveScript
│                                   plus MVP_GOALS (prompt_exfil, state_exfil, policy_override,
│                                   memory_poisoning, tool_hijack, tenant_pivot)
│
├── attack/                       ← attack catalog + payload synthesis
│   ├── base.py                   ← AttackStrategy ABC
│   ├── catalog/loader.py         ← load_test_specs() — parses pluggable catalog JSON
│   ├── library/                  ← built-in catalogs
│   │   ├── direct/               ← direct-chat injection
│   │   ├── indirect/             ← upload/document indirect injection
│   │   ├── memory/               ← memory poisoning
│   │   ├── tools/                ← tool misuse + tool poisoning
│   │   └── data-extraction/      ← agent exfiltration
│   ├── fixtures/                 ← shared fixture-render helpers used by indirect catalogs
│   │   └── render.py             ← {{SESSION_ID}}, {{CANARY_TOKEN}} substitution
│   ├── synthesis/                ← Phase 5 of MUZZLE: payload synthesis
│   │   ├── static_strategy.py    ← StaticStrategy — replays catalog turns as-is
│   │   ├── llm_synth.py          ← LlmSynthStrategy — adaptive LLM mutator
│   │   │                           with compliance classifier + escalation ladder
│   │   └── chain_strategy.py     ← multi-turn chain strategy for PAIR-style flows
│   ├── technique_library.json    ← named techniques, their objectives + surfaces
│   └── technique_selector.py     ← TechniqueSelector — picks technique by (objective, surface)
│
├── oracle/                       ← Phase 7 of MUZZLE: judge agent responses
│   ├── base.py                   ← Oracle ABC
│   ├── pattern_oracle.py         ← regex/heuristic oracle (cheap, deterministic)
│   ├── llm_oracle.py             ← LLM-backed oracle (LlmOracle.evaluate)
│   ├── prescreen.py              ← cheap pre-filter (used by judge.py)
│   └── judge.py                  ← Judge.run() — combines pattern + LLM oracle into JudgeResult
│
├── memory/                       ← cross-cycle state
│   ├── working.py                ← WorkingMemory — per-cycle scratch
│   └── strategic.py              ← StrategicMemory — per-engagement persisted JSON;
│                                   surface_stats, technique_stats, winning_turns, failed_attacks
│
├── triage/
│   └── bandit.py                 ← SurfaceBandit — UCB1 over (surface × technique) arms;
│                                   per-oracle-flag fractional rewards
│
├── reflection/
│   ├── attribution.py            ← FailureReason → SUGGESTIONS map
│   └── controller.py             ← ReflectionController — post-run failure attribution
│
├── budget/
│   ├── tracker.py                ← BudgetTracker — token/cost accounting
│   └── tool_counter.py           ← ToolCallCounter — per-tool budget caps
│
├── campaign/                     ← top-level orchestration
│   ├── runner.py                 ← CampaignRunner — runs Layer 1 (catalog) per scenario
│   ├── scheduler.py              ← Scheduler — drives runner across specs with cost cap
│   ├── muzzle_orchestrator.py    ← MuzzleOrchestrator — runs Layer 2 (adaptive cycles).
│   │                               Has agentic mode (deepagents SubAgents) + scripted mode
│   ├── think_tool.py             ← make_think_tool — structured reasoning capture
│   ├── validator.py              ← AgentValidator — post-cycle quality checks
│   ├── memory_writer.py          ← FindingMemory writer
│   └── context.py                ← shared cycle context object
│
├── reporting/
│   ├── csv_writer.py             ← runs.csv (STANDARD_COLUMNS)
│   ├── jsonl_writer.py           ← runs.jsonl (per-result rows)
│   ├── markdown_reporter.py      ← report.md (human summary)
│   ├── finding_card.py           ← per-finding formatted card
│   └── engagement_report.py      ← multi-cycle engagement summary
│
├── telemetry/                    ← LEGACY (slated for kairos retirement in phase 3)
│   ├── emitter.py                ← TelemetryEmitter (DEPRECATED docstring)
│   ├── events.py                 ← event-name string constants
│   └── langfuse_exporter.py      ← Langfuse integration (DEPRECATED, disconnected)
│
└── integrations/
    └── agentdojo/                ← AgentDojo benchmark integration
        ├── attack.py             ← GraftedAttack(BaseAttack) — the paper's integration
        └── verdict_harvest.py    ← VerdictHarvester — reads (utility, security)
                                    from AgentDojo's logdir for cross-pair memory updates
```

```
scripts/                          ← entry points
├── run_campaign.py               ← main HTTP-victim driver; underlies the `grafted` CLI
├── run_agentdojo.py              ← drives benchmark_suite_with_injections w/ GraftedAttack
└── run_agentdojo_ablation.py     ← runs the per-suite vs per-pair memory ablation

profiles/
└── default.yaml                  ← 10 benign reconnaissance tasks (was hardcoded; now data)

tests/
├── unit/                         ← module-level
├── integration/                  ← end-to-end against the mock victim
└── e2e/                          ← (kept as scaffolding; HR-AI tests stripped in phase 1.2)

docs/
├── getting-started.md            ← quickstart
├── architecture/                 ← THIS FOLDER
├── internal/                     ← TRDs, design discussions, research notes (contributor-only)
└── obsidian/Projects/grafted/Plans/   ← active plan docs
```

## The MUZZLE loop, mapped to files

The seven-step adaptive loop, in the order it executes per cycle. Each step is one phase.

| # | Phase | Purpose | Where it lives | Key entry point |
|---|---|---|---|---|
| 0 | Catalog | Run the pre-engineered attack catalog deterministically before any adaptation | `campaign/runner.py` + `attack/catalog/loader.py` | `CampaignRunner.run_specs()` |
| 1 | Explore | Send benign tasks; classify the agent's responses to surface what it can do | `explorer/explorer.py` + `explorer/llm_classifier.py` | `Explorer.run_task()` |
| 2 | Summarize | Collapse multi-turn exploration into a structured trace per task | `explorer/summarizer.py` | `Summarizer.summarize()` |
| 3 | Graft | For each discovered surface, generate ranked typed attack-vessel candidates | `grafter/grafter.py` | `Grafter.discover()` |
| 4 | Objective Replay | Probe the agent introspectively; LLM-distill the disclosure into an attack imperative | `objective_replay/replayer.py` | `ObjectiveReplayer.run_and_distill()` |
| 5 | Synthesize | Mutate base payloads using the imperative + memory + technique selector | `attack/synthesis/llm_synth.py` | `LlmSynthStrategy.next_turn()` |
| 6 | Execute | Run the synthesized payload against the victim | `campaign/runner.py` | `CampaignRunner.run_one()` |
| 7 | Judge | Pattern oracle + LLM oracle → JudgeResult; update strategic memory + bandit | `oracle/judge.py` | `Judge.run()` |

The full loop driver is `MuzzleOrchestrator.run_cycle()` in `grafted/campaign/muzzle_orchestrator.py` — it has both an **agentic mode** (deepagents SubAgents: Orchestrator + Explorer + Attacker) and a **scripted mode** (direct Python orchestration).

## Where each MUZZLE component differs from a fuzzer

This is the paper's contribution, anchored in code:

- **Surface discovery before attack** — `Explorer` + `LlmResponseClassifier` produce a typed surface set per agent. Fuzzers attack a fixed surface.
- **Typed vessels, not bytes** — `Grafter.discover()` emits `VesselCandidate(vessel_kind, delivery_field, exploit_method)` per surface. Fuzzers mutate strings.
- **Per-victim objective distillation** — `ObjectiveReplayer.distill()` uses an LLM to turn the agent's introspective disclosures into a per-victim attack imperative + context hint. Fuzzers don't have this concept.
- **Cross-cycle strategic memory** — `StrategicMemory` (`grafted/memory/strategic.py`) tracks per-(surface, technique) attempts/successes, winning turns, failed attacks; persisted JSON between cycles. Fuzzers reset per pair.
- **UCB1 bandit allocation** — `SurfaceBandit` (`grafted/triage/bandit.py`) with per-oracle-flag fractional rewards (`canary_exfiltrated=1.0`, `prompt_leak=0.9`, etc.). Fuzzers use binary coverage feedback.
- **Compliance-classified escalation** — `LlmSynthStrategy._classify_compliance()` reads the victim's response, classifies `COMPLIANT/PARTIAL/REFUSAL_SOFT/REFUSAL_HARD/EVASIVE/DONE`, picks the next move from a state-aware ladder. Fuzzers mutate blindly.

## Cross-cutting infrastructure

Things every phase touches.

- **`core/schemas.py`** — every typed object the system passes around: `TestSpec` (a catalog entry), `JudgeResult` (oracle verdict), `RunConfig` (the campaign config), `ExplorationTrace`, `SummarizedTrace`, `VesselCandidate`, `ObjectiveScript`, `FindingMemory`, `JudgeResult`. All Pydantic.
- **`memory/strategic.py`** — `StrategicMemory.save(engagement_id)` / `.load(engagement_id)` round-trip JSON to `reports/{engagement_id}/memory/strategic.json`. The `_to_dict` / `_from_dict` helpers are also used by GraftedAttack with a custom path.
- **`triage/bandit.py`** — `SurfaceBandit.warm_start(strategic_memory)` lets the bandit inherit historical win rates so cycle 0 isn't pure exploration.
- **`telemetry/emitter.py`** — legacy JSONL writer, currently still used by `CampaignRunner`. Marked DEPRECATED; replaced by kairos in phase 3.
- **`reporting/`** — final-write side. `csv_writer` + `jsonl_writer` write per-row results; `markdown_reporter` writes the human report; `engagement_report` aggregates across cycles. Independent of the legacy telemetry retirement.

## What was stripped (phase 1 recap)

To reduce confusion when you read the codebase: the following used to exist and is now gone (recoverable from git history before commit `1497274`):

- **HR-AI lab** — `HrApiAdapter`, 10 catalogs in `attack/library/hr_ai/`, fixtures (resumes, websites, linkedin, shells), 3 shell scripts, 1 migration script (`convert_hr_catalogs.py`), 1 Explorer probe script, 1 unit test. Phase 1.1.
- **DocAI / RAG lab** — `DocAiAdapter`, `attack/library/doc_ai/`, doc-ai fixtures. Phase 1.2.
- **DeepAgent doc-pipeline lab** — `DeepAgentAdapter`, 5 deepagent catalogs, `run_deepagent.py`, 3 HR/private-lab E2E tests, `test_chain_runner.py`. Phase 1.2.
- **Desert smoke + eval_metrics + legacy replay** — desert catalog + script, `run_eval.py`, `convert_fixture.py`, `eval_metrics.py`, `replay_run.py`, `telemetry/replay.py`, replay test. Phase 1.3.
- **HR-flavored fragments inside generic files** — `runner.py`'s html→txt upload conversion, comments in `response_heuristics.py`, four HR-flavored MVP_GOALS in `replayer.py` (renamed/generalized: `score_manipulation` → `policy_override`). Phase 1.4.
- **Langfuse** — disconnected from the active path; `langfuse_exporter.py` and `emitter.py` marked DEPRECATED for full removal in phase 3.7. Phase 1.5.
- **Hardcoded exploration tasks** — `_default_exploration_tasks()` in `run_campaign.py` → `profiles/default.yaml` + `core/profile.py:load_exploration_tasks`. Phase 1.6.
- **Old name** — package `deeppeak-harness`, source `harness/` → `grafted` everywhere internally. GitHub repo URL stays at `akar5h/agentred` until post-paper. Phase 1.7.
- **TRDs at top of `docs/`** — moved to `docs/internal/`. Phase 1.8.

## Dependencies (runtime)

From `pyproject.toml`:

- `pydantic>=2.7` — every typed object
- `httpx>=0.27` — generic HTTP victim adapter, OpenRouter calls
- `fastapi`, `uvicorn`, `python-multipart` — only for the mock victim used by integration tests; could be moved to a test-only dep later
- `langchain-anthropic`, `langchain-openai` — LLM call surfaces (Explorer classifier, ObjectiveReplayer distiller, LlmOracle, LlmSynthStrategy chain mode)
- `deepagents>=0.4.3` — powers `MuzzleOrchestrator` agentic mode (Orchestrator + Explorer + Attacker SubAgents)
- `pyyaml>=6.0` — exploration profile loader (added in phase 1.6)

Optional extras:

- `[agentdojo]` — pulls AgentDojo for the benchmark integration (added in phase 2.2)
- `[observability]` — legacy Langfuse extra (will retire in phase 3 alongside the other telemetry cleanup)

Phase 3 will add: `kairos`, `traceloop-sdk`, `opentelemetry-sdk`, `opentelemetry-exporter-otlp-proto-http`.
