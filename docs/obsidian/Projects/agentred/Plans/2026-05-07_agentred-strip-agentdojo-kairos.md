---
date: 2026-05-07
project: agentred
status: draft
owner: akarsh
related:
  - docs/TRD/00-MUZZLE-LOOP.md
  - docs/TRD/01-EXPLORER.md
  - docs/TRD/02-GRAFTER.md
tags: [plan, agentdojo, kairos, paper, refactor]
---

# agentred — Strip → AgentDojo plumbing → Kairos observability

## Context

`agentred` (current package name `deeppeak-harness`, repo also referred to as "GART") is an MUZZLE-style multi-agent red-teaming harness. The codebase currently mixes:

- A reusable engine (Explorer, Grafter, ObjectiveReplayer, StrategicMemory, Bandit, LlmSynthStrategy, MuzzleOrchestrator, Judge)
- HR-AI lab-specific artifacts (HrApiAdapter, DocAiAdapter, DeepAgentAdapter, 10 HR-specific catalogs, three HR-specific shell scripts, HR-flavored objective goals, HR-specific exploration tasks baked into `run_campaign.py`)
- TRD design docs at the top of `docs/`

The goal for the next ~30 hours of work is to ship an arXiv paper that extends AgentDojo (Debenedetti et al., NeurIPS '24), positioning agentred against AgentVigil as the comparative baseline. The paper's central thesis: **structured surface modeling + cross-task transfer beats per-pair fuzzing**.

To get there cleanly, the codebase needs three things, in order:

1. **Strip** — remove or move out the HR-AI lab artifacts so the repo presents as a generic engine, not a private fork.
2. **AgentDojo plumbing** — adapter that conforms to AgentDojo's `AttackPipeline.attack(user_task, injection_task)` interface, with strategic memory persisted across pairs.
3. **Kairos observability** — every engagement produces TraceEnvelopes (one per AgentDojo pair) via the user's `kairos` SDK on branch `live-sdk`, viewable in Phoenix.

## Goal

After completing all three phases:

- `agentred run --adapter agentdojo --suite workspace --victim gpt-4o-mini` runs end-to-end against AgentDojo's workspace suite.
- One TraceEnvelope per `(user_task, injection_task)` pair lands in `data/live/normalized/`.
- A memory-on-vs-off ablation (the central empirical claim) is reproducible with a single flag flip.
- The repo presents publicly as a generic agent red-teaming engine — no HR-AI lab references in user-facing surface.

## Scope

**In scope:**
- File deletion/moves for HR-AI artifacts
- Adapter registry refactor
- `AgentDojoAdapter` (new)
- Memory scope flag and persistence wiring
- Kairos + Phoenix + Traceloop integration
- Span instrumentation across MuzzleOrchestrator, victim base, judge

**Out of scope (do not touch):**
- Catalog format changes
- Judge/Oracle algorithm changes
- Bandit algorithm changes (UCB1 stays as-is)
- New attack categories
- CLI wizard / `agentred init` (post-paper product work)
- `agentic-rag-lab/`, `rag-redteam/`, `redteam-platform/`, `rt-box/` — different projects in the workspace

## Decisions made

1. **Path (a) for AgentDojo integration** — single-shot `AttackPipeline.attack()` interface. Multi-turn within-task is a v2/ablation, not the headline contribution.
2. **Trace boundary granularity** — one `kairos.task` per `(user_task, injection_task)` pair, not per engagement, not per cycle. Matches TraceEnvelope's per-pair shape and the paper's per-pair ASR analysis.
3. **Memory key** — `f"agentdojo-{suite}-{victim_model}"` with a `--memory-scope` flag taking values `per-suite | per-model | per-pair`. The `per-pair` scope is effectively memory-off, used as the ablation control.
4. **Concurrency** — `max_concurrency=1` enforced when adapter is `agentdojo` (kairos exporter doesn't lock internally per `live-sdk` setup notes).
5. **Editable kairos install** — use `[tool.uv.sources] kairos = { path = "/Users/akarshgajbhiye/kairos", editable = true }` rather than `file://` URL. Avoids `uv sync --reinstall-package` after every kairos change.
6. **Retire** — `harness/telemetry/emitter.py` and `harness/telemetry/langfuse_exporter.py` (kairos + Phoenix subsume them).
7. **Keep** — `BudgetTracker` data model, but switch to setting span attributes instead of in-memory accumulation.
8. **Rename** — package `deeppeak-harness` → `agentred`, source folder `harness/` → `agentred/`, drop "GART" from user-facing surface (keep "MUZZLE" as the algorithm name in code/docs only).

## Open questions

- [ ] Is the AgentDojo adapter going to live inside `agentred` or as a separate `agentred-agentdojo` package? **Recommendation: inside, under `agentred/victim/agentdojo_adapter.py`.** Re-decide if AgentDojo's deps are heavy enough to warrant extra-only.
- [ ] Are AgentDojo experiments running locally or on a remote box? Affects Phoenix setup (local: just `phoenix serve`; remote: SSH tunnel `localhost:6006` or skip live UI and rely on normalized envelopes).
- [ ] Does `harness/campaign/scheduler.py` parallelize scenarios today? Need to confirm before locking concurrency=1 (verify by reading scheduler.py during phase 1).
- [ ] LLM call routing in `harness/attack/synthesis/llm_synth.py:_mutate_via_openrouter` uses raw httpx — Traceloop won't auto-patch it. **Decision needed during phase 3.6:** route through `langchain-openai` (already a dep, gets auto-patched) or wrap manually in a `tracer.start_as_current_span("openai.chat")`.
- [ ] AgentDojo's `AttackPipeline` exact signature — confirm by reading `agentdojo/attacks/base_attacks.py` source before starting phase 2.

## Pre-flight: Week-0 memory ablation experiment (2h, must run first)

Before committing to the full plan, validate the central thesis:

- Run agentred against AgentDojo's workspace suite, 10 `(user_task, injection_task)` pairs, twice:
  - Run A: `--memory-scope per-suite` (memory transfers across pairs)
  - Run B: `--memory-scope per-pair` (memory reset per pair → effectively memory-off)
- Compare ASR.
- **If A > B by a meaningful margin:** thesis works on AgentDojo, proceed with full plan.
- **If A ≈ B:** kill the cross-task framing. Either pivot to multi-turn-within-task (path b) or rethink the contribution before writing the paper.

Note: the experiment script depends on phase 2.2 + 2.3 being done. So the order is: phase 1 → phase 2.1-2.3 → pre-flight → phase 2.4+ → phase 3.

## Phase 1 — Strip (target: 4h)

### 1.1 — Move HR-AI artifacts out (1h)

Files to remove from main tree (move to `examples/private/` and add to `.gitignore`, OR move to a separate private repo):

- `harness/victim/hr_api_adapter.py`
- `harness/victim/doc_ai_adapter.py`
- `harness/victim/deep_agent_adapter.py`
- `harness/attack/library/hr_ai/` (10 catalog files)
- `scripts/run_gart_full.sh`
- `scripts/run_gart_trd24.sh`
- `scripts/run_hr_budget_campaign.sh`
- `fixtures/indirect_v1/` (verify no test references first; if used, keep)

Files to edit:

- `scripts/run_campaign.py` — remove `--hr-ai` and `--doc-ai` flags + their dispatch branches
- `harness/objective_replay/replayer.py` — generalize `MVP_GOALS`. Drop `tenant_pivot`'s "client-techcorp" reference; replace `score_manipulation` and `memory_poisoning` HR-flavored elicitation turns with generic equivalents
- `harness/core/schemas.py:RunConfig` — drop HR-specific fields if any (audit during this step)

### 1.2 — Externalize default exploration tasks (1h)

- Move `_default_exploration_tasks()` body from `scripts/run_campaign.py` into `profiles/default.yaml`
- Add a tiny YAML loader in `agentred/core/profile.py`
- `scripts/run_campaign.py` reads the profile via a `--profile` flag (default: `profiles/default.yaml`)

### 1.3 — Rename package (1.5h)

- `pyproject.toml`: `name = "deeppeak-harness"` → `name = "agentred"`, fix description
- Rename source folder: `harness/` → `agentred/`
- `sed -i 's/from harness/from agentred/g'` and `'s/import harness/import agentred/g'` across all `.py` files (verify with `grep -r "harness" agentred/ scripts/ tests/` after)
- Add `[project.scripts] agentred = "agentred.cli:main"` and create a thin `agentred/cli.py` that re-exports `scripts/run_campaign.py:main` (so `agentred run` works)
- Update README to use `agentred` everywhere

### 1.4 — Documentation hygiene (30min)

- Move TRDs to `docs/internal/`. Top-level `docs/` gets a fresh `getting-started.md` that points at `scripts/run_campaign.py` for now (richer README is a separate scope item).
- Drop the arXiv link from README until the agentred paper is on arXiv. Mention "MUZZLE algorithm — see docs/internal/00-MUZZLE-LOOP.md" instead.
- Update repo-level `README.md` to reflect `agentred` naming and new quickstart shape.

### Phase 1 done condition

- [ ] `pip install -e .` succeeds
- [ ] `agentred --help` works
- [ ] `grep -ri "hr_ai\|techcorp\|deeppeak\|gart" agentred/ scripts/ tests/ docs/ README.md` returns nothing user-facing
- [ ] Existing generic catalogs (`harness/attack/library/{direct,indirect,data-extraction,tools,memory}/`) still load and run via `scripts/run_campaign.py --catalog ...`
- [ ] No HR-AI lab dependency anywhere on the import path

## Phase 2 — AgentDojo plumbing (target: 8h)

### 2.1 — Adapter registry (2h)

- New file `agentred/victim/registry.py` with a `register(name)` decorator and a `get(name) -> VictimAdapter` lookup
- Built-in registrations: `http` → `RestApiAdapter`, `agentdojo` → `AgentDojoAdapter` (after 2.2)
- Custom escape hatch: `--adapter custom:my_pkg.MyAdapter` parsed in `scripts/run_campaign.py`
- Replace the `if args.hr_ai / args.doc_ai / else` block in `_run()` with `victim = registry.build(args.adapter, args)`

### 2.2 — `AgentDojoAdapter` (4h)

New file: `agentred/victim/agentdojo_adapter.py`. Responsibilities:

- Implement AgentDojo's `AttackPipeline.attack(user_task, injection_task) -> dict[str, str]`
- For each call:
  1. Compute `engagement_id` from `--memory-scope` (`f"agentdojo-{suite}-{victim_model}"` for per-suite, etc.)
  2. Load `StrategicMemory` from disk (path keyed by engagement_id)
  3. Open a `kairos.integrations.task` boundary with metadata `{suite, user_task_id, injection_task_id, victim_model, engagement_id, memory_scope}`
  4. Run **one** GART cycle scoped to this pair:
     - Skip Explorer (AgentDojo stipulates the surface)
     - Set `ObjectiveScript.imperative` from `injection_task.GOAL` / description
     - Set `ObjectiveScript.context_hint` from `user_task` description
     - Run synthesis via `LlmSynthStrategy.next_turn(...)` with strategic memory loaded
     - Capture the output string
  5. Write attack string to AgentDojo's expected placeholder dict
  6. Update `StrategicMemory` from the resulting `JudgeResult` (will require AgentDojo's eval result to flow back — see 2.3)
  7. Persist `StrategicMemory` to disk
- Implement other `VictimAdapter` abstract methods (`send_turn`, `upload_file`, `list_docs`, `reset_session`) as no-ops or proxies, since this adapter doesn't drive a victim — AgentDojo does

### 2.3 — Memory persistence + cross-pair learning loop (1.5h)

- Verify `StrategicMemory` round-trips via JSON (already serializes per `harness/memory/strategic.py` — confirm with a unit test)
- Add `--memory-scope` flag to `scripts/run_campaign.py`: `per-suite | per-model | per-pair`, default `per-suite`
- Add `--memory-dir` flag for the on-disk location (default: `data/agentred/memory/`)
- After each `attack()` call, `agentred` doesn't see AgentDojo's eval verdict directly — need a wrapper benchmark runner (`scripts/run_agentdojo.py`) that:
  - Iterates AgentDojo `(user_task, injection_task)` pairs
  - Calls `AgentDojoAdapter.attack()` for each
  - Calls AgentDojo's evaluator
  - Feeds the verdict back into `StrategicMemory.update_from_result(...)`
  - Saves memory before next pair

### 2.4 — Pre-flight experiment harness (30min)

- `scripts/run_agentdojo_ablation.py` that runs the workspace suite twice on the same model, once with `per-suite`, once with `per-pair`, and writes a comparison CSV
- Runs against ~10 pairs first for fast feedback before committing to full suite

### Phase 2 done condition

- [ ] `agentred run --adapter agentdojo --suite workspace --victim gpt-4o-mini --memory-scope per-suite` produces an AgentDojo-format result file
- [ ] The same command with `--memory-scope per-pair` produces a comparable file
- [ ] `StrategicMemory` round-trips cleanly (unit test)
- [ ] `data/agentred/memory/agentdojo-workspace-gpt-4o-mini.json` exists and grows across pairs in the per-suite mode
- [ ] Ablation script produces a side-by-side ASR comparison

## Phase 3 — Kairos observability (target: 5h)

### 3.1 — Add deps (30min)

In `pyproject.toml`:

```toml
[project.dependencies]
# ... existing ...
"kairos",
"traceloop-sdk>=0.40.0",
"opentelemetry-sdk>=1.25.0,<2",
"opentelemetry-exporter-otlp-proto-http>=1.25.0,<2",

[tool.uv.sources]
kairos = { path = "/Users/akarshgajbhiye/kairos", editable = true }
```

Verify with: `uv run python -c "from kairos.integrations import install_live, task; print('ok')"`

### 3.2 — `agentred/observability/kairos_setup.py` (1h)

Direct lift of tau-agent's `kairos_setup.py` pattern. Three functions:

- `install_kairos(raw_dir="data/live/raw") -> JSONLFileSink` — calls `install_live(raw_dir, viewer="phoenix", phoenix_endpoint="http://localhost:6006/v1/traces", auto_instrument=True, set_global=True, auto_close=False)`. Stores handle module-globally.
- `shutdown_kairos()` — flushes the provider and closes the handle.
- `normalize_to_envelopes(raw_dir, out_dir)` — runs `LiveNormalizer.from_jsonl()` over each JSONL and saves via `JSONStore`.

### 3.3 — Trace boundary in `AgentDojoAdapter` (1h)

In `AgentDojoAdapter.attack()`:

```
with kairos.integrations.task(
    name="agentdojo-pair",
    metadata={
        "agentdojo_suite": ...,
        "agentdojo_user_task_id": ...,
        "agentdojo_injection_task_id": ...,
        "victim_model": ...,
        "engagement_id": ...,
        "memory_scope": ...,
    },
):
    # GART cycle here
```

### 3.4 — Phase spans inside the cycle (1.5h)

In `agentred/campaign/muzzle_orchestrator.py`, both `_run_cycle_scripted()` and `_run_cycle_agentic()`:

```
with tracer.start_as_current_span(f"agentred.cycle.{cycle_num}"):
    with tracer.start_as_current_span("agentred.phase.explore"):
        ...
    with tracer.start_as_current_span("agentred.phase.graft"):
        ...
    with tracer.start_as_current_span("agentred.phase.replay"):
        ...
    with tracer.start_as_current_span("agentred.phase.execute"):
        ...
    with tracer.start_as_current_span("agentred.phase.judge"):
        ...
```

Get tracer via `from opentelemetry import trace; tracer = trace.get_tracer("agentred")`.

### 3.5 — `tool.{name}` spans on victim calls (1h)

- New `agentred/observability/decorators.py` with a `@traced_tool(name)` decorator that wraps an async method in `tracer.start_as_current_span(f"tool.{name}")` and sets attributes from args/return value.
- Apply to `VictimAdapter`'s `send_turn`, `upload_file`, `list_docs`, `reset_session` — either at the base class level or on each concrete subclass.
- Same pattern for `Judge.run()` → `tool.judge`, `LlmOracle.evaluate()` → `tool.llm_oracle`, `PatternOracle.evaluate()` → `tool.pattern_oracle`.

### 3.6 — Resolve raw-httpx LLM calls (30min)

`harness/attack/synthesis/llm_synth.py:_mutate_via_openrouter` uses `httpx.AsyncClient` directly. Decision: route through `langchain_openai.ChatOpenAI` (already imported elsewhere in the file) so Traceloop auto-patches it. Same for any other raw httpx LLM call — audit during this step.

If routing isn't trivial, fallback: wrap the call site in `tracer.start_as_current_span("openai.chat")` with attributes `gen_ai.system`, `gen_ai.request.model`, `gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens` set manually.

### 3.7 — Retire old telemetry (1h)

- Delete `harness/telemetry/emitter.py` (kairos's sink replaces it). Audit all callers — likely just `scripts/run_campaign.py` and `MuzzleOrchestrator`.
- Delete `harness/telemetry/langfuse_exporter.py` and the `LangfuseExporter.from_env()` call in `scripts/run_campaign.py`. Phoenix replaces the live viewer role.
- Repurpose `BudgetTracker`: keep the data model but make `record()` set span attributes (`tokens.in`, `tokens.out`, `cost.usd`) on the active span instead of accumulating internally. The TraceEnvelope rolls them up via `total_tokens`.
- Keep `harness/reporting/{csv_writer,jsonl_writer,markdown_reporter}.py` — they consume per-result rows, not telemetry; orthogonal to this phase.
- `run_meta.json` — keep as a flat run summary, but derive it post-run from events.jsonl rather than from in-memory state.

### 3.8 — Wire into `scripts/run_campaign.py` (30min)

- At process start (top of `_run()`): `install_kairos(raw_dir=run_dir / "live" / "raw")`
- At process end (after the `with TelemetryEmitter` block today, replaced by kairos): `shutdown_kairos()` then `normalize_to_envelopes(raw_dir, run_dir / "live" / "normalized")`

### Phase 3 done condition

- [ ] Run completes and Phoenix UI at `localhost:6006` shows a flame chart per `(user_task, injection_task)` pair
- [ ] `data/live/raw/<trace_id>.jsonl` files exist post-run
- [ ] `data/live/normalized/<trace_id>.json` files exist post-run, conform to `TraceEnvelope`
- [ ] One TraceEnvelope inspect via the verification script in §6 of the kairos setup doc shows non-zero `step_count`, populated `tool_sequence`, and `terminal_status` set
- [ ] Token usage attributes appear on `openai.chat`-named spans (either auto from Traceloop or manual)

## Test/verification checklist

After all three phases:

- [ ] `pytest tests/` passes (existing test suite, post-rename)
- [ ] `agentred --help` lists `--adapter`, `--memory-scope`, `--profile` flags
- [ ] `agentred run --adapter http --base-url http://localhost:8000 --catalog harness/attack/library/direct/direct_chat_injection_v1.json` runs (smoke against generic adapter to confirm the engine still works post-strip)
- [ ] `agentred run --adapter agentdojo --suite workspace --victim gpt-4o-mini --memory-scope per-pair` runs against ~3 pairs
- [ ] Phoenix shows traces in real-time during the run
- [ ] Pre-flight memory ablation script produces a comparison CSV with non-trivial ASR delta (paper-defining)
- [ ] No reference to "hr_ai", "techcorp", "deeppeak", "GART" in the public surface (`README.md`, `pyproject.toml`, `agentred/`, `scripts/`)

## Rollback plan

Each phase commits independently:

- **Phase 1 rollback:** `git revert` the strip commit. HR-AI artifacts move back into the main tree.
- **Phase 2 rollback:** disable the adapter registry, restore `--hr-ai`/`--doc-ai` dispatch. AgentDojoAdapter stays in `examples/` as inert code.
- **Phase 3 rollback:** if kairos breaks something, the legacy `TelemetryEmitter` and `LangfuseExporter` should be retained on a `legacy/` path until phase 3 is verified, not deleted. Switch back via env var.

Never force-push the working branch (`claude/gart-wrapper-review-SPGv2`); revert and recommit if needed.

## Done criteria (the entire plan)

1. Repo presents publicly as `agentred` — generic engine, no private-lab residue.
2. AgentDojo adapter runs end-to-end against the workspace suite, with memory persisted and a flag-flippable ablation.
3. Every run produces TraceEnvelopes one-per-pair via kairos, viewable in Phoenix during the run.
4. The week-0 memory ablation has been run, and its result determines whether the paper proceeds with the cross-task-transfer thesis or pivots.
5. The arXiv submission timeline (week 1 plumbing, week 2 experiments, week 3 draft, week 4 ship) starts from a clean codebase.

## Notes for follow-up plans

These are explicitly **out of scope** for this plan but worth tracking for after:

- Public README rewrite (post-paper, with arXiv BibTeX)
- `agentred init` wizard (post-paper product work)
- LangGraph adapter (post-paper, the "scanner product" angle)
- Catalog format → "scan packs" rename
- CI / `agentred doctor` command
