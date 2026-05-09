---
date: 2026-05-07
project: grafted
status: draft
owner: akarsh
related:
  - docs/TRD/00-MUZZLE-LOOP.md
  - docs/TRD/01-EXPLORER.md
  - docs/TRD/02-GRAFTER.md
tags: [plan, agentdojo, kairos, paper, refactor, naming]
---

# grafted — Strip → AgentDojo plumbing → Kairos observability

## Context

The project formerly known internally as "GART" / "MUZZLE harness" / package `deeppeak-harness` is being renamed **grafted**. The name comes from Elden Ring (Godrick the Grafted attaches stolen limbs and powers onto himself), and matches the codebase architecture exactly — the existing `Grafter` component attaches typed attack vessels onto discovered surfaces.

The GitHub repo URL stays at `github.com/akar5h/agentred` for now — repo rename is **out of scope for this plan**. Only internal naming (package, source folder, CLI, scripts, docs) changes.

The codebase currently mixes:

- A reusable engine (Explorer, Grafter, ObjectiveReplayer, StrategicMemory, Bandit, LlmSynthStrategy, MuzzleOrchestrator, Judge)
- Three private-lab adapter families and their attack catalogs/fixtures/scripts:
  - HR-AI lab (`HrApiAdapter`, 10 catalogs, fixtures, 3 shell scripts, multiple Python scripts)
  - DocAI / RAG lab (`DocAiAdapter`, 1 catalog, fixtures)
  - DeepAgent doc-pipeline lab (`DeepAgentAdapter`, 5 catalogs, 1 script)
- A "desert" smoke catalog + script + `eval_metrics` module that's tangential to the AgentDojo scope
- TRD design docs at the top of `docs/`

The goal for the next ~30 hours of work is to ship an arXiv paper that extends AgentDojo (Debenedetti et al., NeurIPS '24), positioning grafted against AgentVigil as the comparative baseline. The paper's central thesis: **structured surface modeling + cross-task transfer beats per-pair fuzzing**.

To get there cleanly, the codebase needs three things, in order:

1. **Strip** — remove or move out the three private labs' artifacts, the desert smoke, eval_metrics, the legacy replay infra, and rename to `grafted` so the repo presents as a generic engine, not a private fork.
2. **AgentDojo plumbing** — adapter that conforms to AgentDojo's `AttackPipeline.attack(user_task, injection_task)` interface, with strategic memory persisted across pairs.
3. **Kairos observability** — every engagement produces TraceEnvelopes (one per AgentDojo pair) via the user's `kairos` SDK on branch `live-sdk`, viewable in Phoenix.

## Goal

After completing all three phases:

- `grafted run --adapter agentdojo --suite workspace --victim gpt-4o-mini` runs end-to-end against AgentDojo's workspace suite.
- One TraceEnvelope per `(user_task, injection_task)` pair lands in `data/live/normalized/`.
- A memory-on-vs-off ablation (the central empirical claim) is reproducible with a single flag flip.
- The repo presents publicly as a generic agent red-teaming engine — no HR-AI / DocAI / DeepAgent lab references, no "GART" / "MUZZLE-harness" / "deeppeak" branding in user-facing surface.

## Scope

**In scope:**
- File deletion/moves for HR-AI, DocAI, DeepAgent, desert artifacts
- Eval_metrics + scripts that depend on it
- Legacy replay infra retirement (kairos JSONL is the new replay path)
- Surgical cleanup of HR-flavored fragments inside otherwise-generic files
- Internal rename: package, source folder, CLI, scripts, docs → `grafted`
- Adapter registry refactor
- `AgentDojoAdapter` (new)
- Memory scope flag and persistence wiring
- Kairos + Phoenix + Traceloop integration
- Span instrumentation across MuzzleOrchestrator, victim base, judge

**Out of scope (do not touch):**
- GitHub repo rename (`akar5h/agentred` stays)
- Catalog format changes
- Judge/Oracle algorithm changes
- Bandit algorithm changes (UCB1 stays as-is)
- New attack categories
- CLI wizard / `grafted init` (post-paper product work)
- Public README rewrite (post-paper)
- LangGraph adapter (post-paper)
- `agentic-rag-lab/`, `rag-redteam/`, `redteam-platform/`, `rt-box/` — different projects in the workspace

## Decisions made

1. **Name = `grafted`.** Package `grafted`, source folder `grafted/`, CLI `grafted`, console script `grafted = "grafted.cli:main"`. No "agentred", no "GART", no "deeppeak", no "MUZZLE-harness" in user-facing surface. "MUZZLE" stays only as the algorithm name in code/docs.
2. **GitHub repo URL stays at `akar5h/agentred`** for the duration of this plan. Repo rename is a separate decision, post-paper.
3. **Path (a) for AgentDojo integration** — single-shot `AttackPipeline.attack()` interface. Multi-turn within-task is a v2/ablation, not the headline contribution.
4. **Trace boundary granularity** — one `kairos.task` per `(user_task, injection_task)` pair, not per engagement, not per cycle.
5. **Memory key** — `f"agentdojo-{suite}-{victim_model}"` with a `--memory-scope` flag taking values `per-suite | per-model | per-pair`. The `per-pair` scope is effectively memory-off, used as the ablation control.
6. **Concurrency** — `max_concurrency=1` enforced when adapter is `agentdojo` (kairos exporter doesn't lock internally per `live-sdk` setup notes).
7. **Editable kairos install** — use `[tool.uv.sources] kairos = { path = "/Users/akarshgajbhiye/kairos", editable = true }` rather than `file://` URL.
8. **Retire** — `harness/telemetry/emitter.py`, `harness/telemetry/langfuse_exporter.py`, `harness/telemetry/events.py`, **and the legacy replay infra** (`harness/telemetry/replay.py` + `scripts/replay_run.py` + `tests/integration/test_replay.py`). Kairos JSONL via `LiveNormalizer.from_jsonl` becomes the canonical replay path.
9. **Keep** — `BudgetTracker` data model, but switch to setting span attributes instead of in-memory accumulation.
10. **Strip the desert smoke** — `harness/attack/library/desert/`, `scripts/run_desert.py`, `harness/campaign/eval_metrics.py`, `tests/unit/test_eval_metrics.py`. Tangential to the AgentDojo scope; if we want a smoke later, easier to re-add than to maintain through the rename.

## Open questions

- [ ] Is the AgentDojo adapter going to live inside `grafted` or as a separate `grafted-agentdojo` package? **Recommendation: inside, under `grafted/victim/agentdojo_adapter.py`.** Re-decide if AgentDojo's deps are heavy enough to warrant extra-only.
- [ ] Are AgentDojo experiments running locally or on a remote box? Affects Phoenix setup (local: just `phoenix serve`; remote: SSH tunnel `localhost:6006` or skip live UI and rely on normalized envelopes).
- [ ] Does `harness/campaign/scheduler.py` parallelize scenarios today? Need to confirm before locking concurrency=1 (verify by reading scheduler.py during phase 1).
- [ ] LLM call routing in `harness/attack/synthesis/llm_synth.py:_mutate_via_openrouter` uses raw httpx — Traceloop won't auto-patch it. **Decision needed during phase 3.6:** route through `langchain-openai` (already a dep, gets auto-patched) or wrap manually in a `tracer.start_as_current_span("openai.chat")`.
- [ ] AgentDojo's `AttackPipeline` exact signature — confirm by reading `agentdojo/attacks/base_attacks.py` source before starting phase 2.
- [ ] `tests/integration/test_chain_runner.py` — verify whether it targets the deepagent private lab; if yes, strip; if generic, keep.

## Pre-flight: Week-0 memory ablation experiment (2h, must run first)

Before committing to the full plan, validate the central thesis:

- Run grafted against AgentDojo's workspace suite, 10 `(user_task, injection_task)` pairs, twice:
  - Run A: `--memory-scope per-suite` (memory transfers across pairs)
  - Run B: `--memory-scope per-pair` (memory reset per pair → effectively memory-off)
- Compare ASR.
- **If A > B by a meaningful margin:** thesis works on AgentDojo, proceed with full plan.
- **If A ≈ B:** kill the cross-task framing. Either pivot to multi-turn-within-task (path b) or rethink the contribution before writing the paper.

Note: the experiment script depends on phase 2.2 + 2.3 being done. So the order is: phase 1 → phase 2.1-2.3 → pre-flight → phase 2.4+ → phase 3.

## Phase 1 — Strip (target: 8h)

Phase 1 grew from a half-day estimate after a deeper sweep — there are three private-lab footprints to remove (HR-AI, DocAI, DeepAgent), plus desert/eval_metrics/replay, plus the rename, plus surgical fixes inside generic files.

### 1.1 — HR-AI lab artifacts (1h)

Files to remove from main tree (move to `examples/private/` and add to `.gitignore`, OR move to a separate private repo):

- `harness/victim/hr_api_adapter.py`
- `harness/attack/library/hr_ai/` (10 catalog files)
- `harness/attack/fixtures/hr_ai/` (resumes/, websites/, linkedin/, shells/)
- `scripts/run_gart_full.sh`
- `scripts/run_gart_trd24.sh`
- `scripts/run_hr_budget_campaign.sh`
- `scripts/convert_hr_catalogs.py` — one-shot migration tool from upstream `hr_ai_redteam`; has done its job
- `scripts/run_surface_discovery.py` — explicitly HR-AI per its docstring

Files to edit:

- `scripts/run_campaign.py` — remove `--hr-ai` flag + dispatch branch (the registry refactor in 2.1 will replace it cleanly)
- `tests/unit/test_hr_api_adapter.py` — delete

### 1.2 — DocAI + DeepAgent lab artifacts (1h)

DocAI (RAG/doc-ai lab):

- `harness/victim/doc_ai_adapter.py`
- `harness/attack/library/doc_ai/doc_ai_injection_v1.json`
- `harness/attack/fixtures/doc_ai/` (poisoned_report.md, rag_poison_report.md, tool_trigger_report.md)

DeepAgent (deepagent-doc-pipeline lab — distinct from the `deepagents` PyPI dep, which stays):

- `harness/victim/deep_agent_adapter.py`
- `harness/attack/library/deepagent/` (5 catalog files)
- `scripts/run_deepagent.py`
- `tests/integration/test_chain_runner.py` — verify deepagent targeting first; if generic, keep; if not, delete
- `fixtures/indirect_v1/` (top-level fixtures dir — verify no test references; if used, keep)

Files to edit:

- `scripts/run_campaign.py` — remove `--doc-ai` flag + dispatch branch
- `tests/e2e/test_phase_t0.py`, `tests/e2e/test_phase_t2.py`, `tests/e2e/conftest.py` — these are HR-AI E2E tests; delete

### 1.3 — Desert smoke + eval_metrics + legacy replay (1h)

- `harness/attack/library/desert/desert_capability_v1.json`
- `scripts/run_desert.py`
- `scripts/run_eval.py` — scripted-vs-agentic comparison; tangential to AgentDojo scope
- `scripts/convert_fixture.py` — fixture converter, only useful for the HR fixture pipeline
- `harness/campaign/eval_metrics.py`
- `tests/unit/test_eval_metrics.py`
- `harness/telemetry/replay.py`
- `harness/telemetry/events.py` (event-name string constants only used by the legacy emitter)
- `scripts/replay_run.py`
- `tests/integration/test_replay.py`

Note: `harness/telemetry/emitter.py` and `harness/telemetry/langfuse_exporter.py` are also retired in this phase per decision 8 — they get deleted in 1.5 alongside the other telemetry retirement, since callers in `MuzzleOrchestrator` and `run_campaign.py` need to stay compilable until phase 3 wires kairos in.

### 1.4 — Surgical cleanup inside generic files (1h)

These files are otherwise generic but have HR-AI flavored fragments:

- **`harness/campaign/runner.py:115-123`** — drop the HR-AI-only `.html → .txt` upload conversion. Pass extension as-is.
- **`harness/core/response_heuristics.py:43`** — drop the `# HR AI / conversational refusal patterns` comment. Patterns themselves are generic, keep them.
- **`harness/objective_replay/replayer.py:MVP_GOALS`** — generalize:
  - `score_manipulation` → `policy_override` (drop "hiring rubric", "candidate evaluation")
  - `memory_poisoning` → drop "team preference for future evaluations" framing
  - `tenant_pivot` → drop "client am I currently working with"; generic tenant-boundary probes
  - `tool_hijack` → replace `submit_evaluation` reference with a generic example tool name
- **`harness/core/schemas.py`** — audit for any HR-specific `RunConfig` fields and drop them

### 1.5 — Telemetry callers + emitter retirement prep (1h)

The legacy emitter retires fully in phase 3.7 once kairos is wired. In phase 1 we only need the scaffold:

- Keep `harness/telemetry/emitter.py` and `harness/telemetry/langfuse_exporter.py` compilable but mark with a deprecation comment
- Drop the `LangfuseExporter.from_env()` import and call in `scripts/run_campaign.py` (langfuse is the first thing to go since it's purely additive)
- Audit all callers of `TelemetryEmitter` (likely `MuzzleOrchestrator`, `CampaignRunner`, `run_campaign.py`) and confirm they degrade cleanly when the emitter is a no-op

This avoids a massive simultaneous refactor in phase 3 and lets phase 2 land in a stable state.

### 1.6 — Externalize default exploration tasks (1h)

- Move `_default_exploration_tasks()` body from `scripts/run_campaign.py` into `profiles/default.yaml`
- Add a tiny YAML loader in `grafted/core/profile.py`
- `scripts/run_campaign.py` reads the profile via a `--profile` flag (default: `profiles/default.yaml`)

### 1.7 — Rename to `grafted` (2h)

- `pyproject.toml`: `name = "deeppeak-harness"` → `name = "grafted"`, fix description
- Rename source folder: `harness/` → `grafted/`
- `sed -i 's/from harness/from grafted/g'` and `'s/import harness/import grafted/g'` across all `.py` files
- Verify: `grep -r "harness" grafted/ scripts/ tests/` after the sed; expect only intentional references
- Update logger names: `logging.getLogger("harness.X")` → `logging.getLogger("grafted.X")` across all modules
- Add `[project.scripts] grafted = "grafted.cli:main"` and create a thin `grafted/cli.py` that re-exports `scripts/run_campaign.py:main` (so `grafted run` works)
- Update README to use `grafted` everywhere; drop "GART", "deeppeak", "MUZZLE-harness", and "agentred" from user-facing surface

### 1.8 — Documentation hygiene (1h)

- `mkdir -p docs/internal && git mv docs/TRD docs/internal/TRD`
- `git mv docs/architecture docs/internal/architecture`
- `git mv docs/research docs/internal/research`
- Top-level `docs/` gets a fresh `getting-started.md` that points at `scripts/run_campaign.py` for now (richer README is a separate scope item, post-paper)
- Drop the arXiv link from README until the grafted paper is on arXiv. Mention "MUZZLE algorithm — see docs/internal/TRD/00-MUZZLE-LOOP.md" instead
- `docs/obsidian/Projects/grafted/Plans/` — keep as-is (this plan lives here)

### Phase 1 done condition

- [ ] `pip install -e .` succeeds
- [ ] `grafted --help` works
- [ ] `grep -ri "hr_ai\|techcorp\|deeppeak\|GART\|agentred\|hiring rubric\|deepagent-doc-pipeline" grafted/ scripts/ tests/ docs/ README.md pyproject.toml` returns nothing user-facing
- [ ] Generic catalogs (`grafted/attack/library/{direct,indirect,data-extraction,tools,memory}/`) still load and run via `scripts/run_campaign.py --catalog ...`
- [ ] `pytest tests/` passes (post-strip suite)
- [ ] `git mv` history is preserved for renamed files
- [ ] No private-lab dependency anywhere on the import path

## Phase 2 — AgentDojo plumbing (target: 8h)

### 2.1 — Adapter registry (2h)

- New file `grafted/victim/registry.py` with a `register(name)` decorator and a `get(name) -> VictimAdapter` lookup
- Built-in registrations: `http` → `RestApiAdapter`, `agentdojo` → `AgentDojoAdapter` (after 2.2)
- Custom escape hatch: `--adapter custom:my_pkg.MyAdapter` parsed in `scripts/run_campaign.py`
- Replace any remaining adapter dispatch in `_run()` with `victim = registry.build(args.adapter, args)`

### 2.2 — `AgentDojoAdapter` (4h)

New file: `grafted/victim/agentdojo_adapter.py`. Responsibilities:

- Implement AgentDojo's `AttackPipeline.attack(user_task, injection_task) -> dict[str, str]`
- For each call:
  1. Compute `engagement_id` from `--memory-scope` (`f"agentdojo-{suite}-{victim_model}"` for per-suite, etc.)
  2. Load `StrategicMemory` from disk (path keyed by engagement_id)
  3. Open a `kairos.integrations.task` boundary with metadata `{suite, user_task_id, injection_task_id, victim_model, engagement_id, memory_scope}`
  4. Run **one** MUZZLE cycle scoped to this pair:
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

- Verify `StrategicMemory` round-trips via JSON (already serializes per `grafted/memory/strategic.py` — confirm with a unit test)
- Add `--memory-scope` flag to `scripts/run_campaign.py`: `per-suite | per-model | per-pair`, default `per-suite`
- Add `--memory-dir` flag for the on-disk location (default: `data/grafted/memory/`)
- Wrapper benchmark runner `scripts/run_agentdojo.py` that:
  - Iterates AgentDojo `(user_task, injection_task)` pairs
  - Calls `AgentDojoAdapter.attack()` for each
  - Calls AgentDojo's evaluator
  - Feeds the verdict back into `StrategicMemory.update_from_result(...)`
  - Saves memory before next pair

### 2.4 — Pre-flight experiment harness (30min)

- `scripts/run_agentdojo_ablation.py` that runs the workspace suite twice on the same model, once with `per-suite`, once with `per-pair`, and writes a comparison CSV
- Runs against ~10 pairs first for fast feedback before committing to full suite

### Phase 2 done condition

- [ ] `grafted run --adapter agentdojo --suite workspace --victim gpt-4o-mini --memory-scope per-suite` produces an AgentDojo-format result file
- [ ] The same command with `--memory-scope per-pair` produces a comparable file
- [ ] `StrategicMemory` round-trips cleanly (unit test)
- [ ] `data/grafted/memory/agentdojo-workspace-gpt-4o-mini.json` exists and grows across pairs in the per-suite mode
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

### 3.2 — `grafted/observability/kairos_setup.py` (1h)

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
    # MUZZLE cycle here
```

### 3.4 — Phase spans inside the cycle (1.5h)

In `grafted/campaign/muzzle_orchestrator.py`, both `_run_cycle_scripted()` and `_run_cycle_agentic()`:

```
with tracer.start_as_current_span(f"grafted.cycle.{cycle_num}"):
    with tracer.start_as_current_span("grafted.phase.explore"):
        ...
    with tracer.start_as_current_span("grafted.phase.graft"):
        ...
    with tracer.start_as_current_span("grafted.phase.replay"):
        ...
    with tracer.start_as_current_span("grafted.phase.execute"):
        ...
    with tracer.start_as_current_span("grafted.phase.judge"):
        ...
```

Get tracer via `from opentelemetry import trace; tracer = trace.get_tracer("grafted")`.

### 3.5 — `tool.{name}` spans on victim calls (1h)

- New `grafted/observability/decorators.py` with a `@traced_tool(name)` decorator that wraps an async method in `tracer.start_as_current_span(f"tool.{name}")` and sets attributes from args/return value.
- Apply to `VictimAdapter`'s `send_turn`, `upload_file`, `list_docs`, `reset_session` — either at the base class level or on each concrete subclass.
- Same pattern for `Judge.run()` → `tool.judge`, `LlmOracle.evaluate()` → `tool.llm_oracle`, `PatternOracle.evaluate()` → `tool.pattern_oracle`.

### 3.6 — Resolve raw-httpx LLM calls (30min)

`grafted/attack/synthesis/llm_synth.py:_mutate_via_openrouter` uses `httpx.AsyncClient` directly. Decision: route through `langchain_openai.ChatOpenAI` (already imported elsewhere in the file) so Traceloop auto-patches it. Same for any other raw httpx LLM call — audit during this step.

If routing isn't trivial, fallback: wrap the call site in `tracer.start_as_current_span("openai.chat")` with attributes `gen_ai.system`, `gen_ai.request.model`, `gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens` set manually.

### 3.7 — Retire old telemetry (1h)

- Delete `grafted/telemetry/emitter.py` (kairos's sink replaces it). Audit all callers — likely `scripts/run_campaign.py` and `MuzzleOrchestrator`.
- Delete `grafted/telemetry/langfuse_exporter.py` (already disconnected in 1.5).
- Delete `grafted/telemetry/events.py` (already retired in 1.3).
- Repurpose `BudgetTracker`: keep the data model but make `record()` set span attributes (`tokens.in`, `tokens.out`, `cost.usd`) on the active span instead of accumulating internally. The TraceEnvelope rolls them up via `total_tokens`.
- Keep `grafted/reporting/{csv_writer,jsonl_writer,markdown_reporter}.py` — they consume per-result rows, not telemetry; orthogonal to this phase.
- `run_meta.json` — keep as a flat run summary, but derive it post-run from events.jsonl rather than from in-memory state.

### 3.8 — Wire into `scripts/run_campaign.py` (30min)

- At process start (top of `_run()`): `install_kairos(raw_dir=run_dir / "live" / "raw")`
- At process end (where the legacy emitter context manager used to close): `shutdown_kairos()` then `normalize_to_envelopes(raw_dir, run_dir / "live" / "normalized")`

### Phase 3 done condition

- [ ] Run completes and Phoenix UI at `localhost:6006` shows a flame chart per `(user_task, injection_task)` pair
- [ ] `data/live/raw/<trace_id>.jsonl` files exist post-run
- [ ] `data/live/normalized/<trace_id>.json` files exist post-run, conform to `TraceEnvelope`
- [ ] One TraceEnvelope inspect via the verification script in §6 of the kairos setup doc shows non-zero `step_count`, populated `tool_sequence`, and `terminal_status` set
- [ ] Token usage attributes appear on `openai.chat`-named spans (either auto from Traceloop or manual)

## Test/verification checklist

After all three phases:

- [ ] `pytest tests/` passes (post-strip, post-rename suite)
- [ ] `grafted --help` lists `--adapter`, `--memory-scope`, `--profile` flags
- [ ] `grafted run --adapter http --base-url http://localhost:8000 --catalog grafted/attack/library/direct/direct_chat_injection_v1.json` runs (smoke against generic adapter to confirm the engine still works post-strip)
- [ ] `grafted run --adapter agentdojo --suite workspace --victim gpt-4o-mini --memory-scope per-pair` runs against ~3 pairs
- [ ] Phoenix shows traces in real-time during the run
- [ ] Pre-flight memory ablation script produces a comparison CSV with non-trivial ASR delta (paper-defining)
- [ ] No reference to "hr_ai", "techcorp", "deeppeak", "GART", "agentred", "deepagent-doc-pipeline" in the public surface (`README.md`, `pyproject.toml`, `grafted/`, `scripts/`)

## Rollback plan

Each phase commits independently:

- **Phase 1 rollback:** `git revert` the strip commits (split per sub-phase: 1.1-1.5 are independently revertable). Private-lab artifacts move back into the main tree. Rename can be reverted as a single sed pass back to `harness`.
- **Phase 2 rollback:** disable the adapter registry, restore generic adapter dispatch. AgentDojoAdapter stays in `examples/` as inert code.
- **Phase 3 rollback:** if kairos breaks something, the legacy emitter/langfuse should be retained on a `legacy/` path until phase 3 is verified, not deleted. Switch back via env var. (Note: this contradicts decision 8's "retire" — pragmatic compromise is to keep legacy code in a `legacy/` folder for 1 commit cycle, then delete in a follow-up commit once kairos is verified stable.)

Never force-push the working branch (`claude/gart-wrapper-review-SPGv2`); revert and recommit if needed.

## Done criteria (the entire plan)

1. Repo presents publicly as `grafted` — generic engine, no private-lab residue, no legacy naming.
2. AgentDojo adapter runs end-to-end against the workspace suite, with memory persisted and a flag-flippable ablation.
3. Every run produces TraceEnvelopes one-per-pair via kairos, viewable in Phoenix during the run.
4. The week-0 memory ablation has been run, and its result determines whether the paper proceeds with the cross-task-transfer thesis or pivots.
5. The arXiv submission timeline (week 1 plumbing, week 2 experiments, week 3 draft, week 4 ship) starts from a clean codebase.

## Total budget

- Phase 1 (strip + rename): ~8h
- Phase 2 (AgentDojo plumbing): ~8h
- Phase 3 (kairos observability): ~5h
- Pre-flight memory ablation: ~2h
- **Total: ~23h focused work**

Fits inside week 1 with buffer (the original 8h/week estimate was light by ~3x — this is a more honest scoping).

## Notes for follow-up plans

These are explicitly **out of scope** for this plan but worth tracking for after:

- GitHub repo rename (`akar5h/agentred` → `akar5h/grafted`)
- Public README rewrite (post-paper, with arXiv BibTeX)
- `grafted init` wizard (post-paper product work)
- LangGraph adapter (post-paper, the "scanner product" angle)
- Catalog format → "scan packs" rename
- CI / `grafted doctor` command
- Re-add a generic smoke catalog if useful for new contributors
