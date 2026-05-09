---
date: 2026-05-07
status: stable
audience: contributors, the author rebuilding context
---

# 02 — Execution flow: what happens when grafted runs

The dynamic view. Companion to [`01-components.md`](01-components.md) which covers the static view (what each module is). Here we trace what happens, step by step, from "user runs grafted" to "report is written" — for both the HTTP campaign path and the AgentDojo integration.

## The two execution paths

grafted has two top-level run modes:

| Mode | Entry point | Use when |
|---|---|---|
| **HTTP campaign** | `grafted` CLI → `scripts/run_campaign.py` | You have an agent reachable via HTTP and want to red-team it with the full MUZZLE loop |
| **AgentDojo benchmark** | `python scripts/run_agentdojo.py` | You want grafted to produce attack strings inside AgentDojo's standardized benchmark, for the paper |

They share most of the engine — the difference is what drives the outer loop and where the agent under test lives.

---

## Path A — HTTP campaign

`grafted --catalog <path> --base-url <url> [--adaptive] [--profile <yaml>]`

### Step 1 — Parse + load (`scripts/run_campaign.py:_run`)

1. argparse parses flags. Key ones:
   - `--catalog` — pre-engineered attack catalog JSON (e.g., `grafted/attack/library/direct/direct_chat_injection_v1.json`)
   - `--base-url` — the victim's HTTP URL
   - `--adapter` — registry key (default `http`); could be `custom:my_pkg.MyAdapter`
   - `--profile` — YAML defining the Explorer's benign tasks (default `profiles/default.yaml`)
   - `--adaptive` — turn on Layer 2 LLM-based synthesis
   - `--engagement-id` — auto-generated if omitted; scopes memory + report folder
2. Build a `RunConfig` from the args. Compute `run_dir` (e.g., `reports/<engagement-id>/<timestamp>_<mode>_<catalog>/`).
3. Load the attack catalog → `list[TestSpec]` via `attack/catalog/loader.py`.

### Step 2 — Build adapter via registry

```python
victim = victim_registry.build(args.adapter, base_url=..., target_mode=...)
```

This dispatches through `grafted/victim/registry.py`. Built-in `http` returns `RestApiAdapter`. Custom escape hatch: `custom:my_pkg.MyAdapter`.

### Step 3 — Build attack strategy

If `--adaptive`:
```python
strategy = LlmSynthStrategy(endpoint, api_key, model_name, ...)
```
Otherwise:
```python
strategy = StaticStrategy()  # replays catalog turns verbatim
```

### Step 4 — Build Judge

```python
judge = Judge(pattern_oracle=PatternOracle(), llm_oracle=LlmOracle(...))
```

Pattern oracle is cheap and deterministic (regex over response text). LLM oracle is expensive but catches semantic wins. Judge uses pattern first, calls LLM only on ambiguous cases.

### Step 5 — Layer 1: catalog execution (deterministic)

```python
runner = CampaignRunner(victim, strategy, judge, emitter, config)
scheduler = Scheduler(runner=runner, max_cost_usd=...)
await scheduler.run(specs=specs, runs_per_scenario=N, on_result=on_result)
```

For each `TestSpec` in the catalog:
1. `runner.run_one(spec)` opens a session with the victim
2. If the spec has `vessel.fixture_path`, load + render the fixture (via `attack/fixtures/render.py`) and `victim.upload_file()` it
3. For each turn in the spec: send via `victim.send_turn()`, capture response
4. `judge.run(spec, transcript)` → `JudgeResult` (status + oracle codes)
5. `on_result(...)` appends to `runs.jsonl` + accumulates for `runs.csv`
6. `TelemetryEmitter` writes events to `telemetry.jsonl` (legacy; kairos in phase 3)

This is reproducible across runs and provides the deterministic baseline numbers in any report.

### Step 6 — Layer 2: MUZZLE adaptive loop

If `--no-muzzle` is NOT set:

```python
orchestrator = MuzzleOrchestrator(victim, runner, config)
cycle_results = await orchestrator.run(
    load_exploration_tasks(args.profile),  # 10 benign tasks from YAML
    on_result=on_result,
)
```

`MuzzleOrchestrator.run()` runs N cycles (default 3). Each cycle is one full MUZZLE loop. Two execution modes:

- **Agentic mode** (preferred when API key set): builds a `create_deep_agent` with three SubAgents (Orchestrator, Explorer, Attacker) and lets it stream through the cycle, with HITL interrupt points (`novel_surface`, `partial_ambiguous`, etc.).
- **Scripted mode** (fallback): direct Python orchestration — same phases, no SubAgent dance.

Per-cycle phase order (scripted mode):

1. **Explore** — for each `ExplorationTask` (from the YAML profile), `Explorer.run_task()` runs the benign turns against the victim, captures the trace.
2. **Classify** — `LlmResponseClassifier` reads each response; surfaces (e.g., `tool_calling`, `file_upload`, `external_api`) get tagged.
3. **Summarize** — `Summarizer.summarize()` collapses the multi-turn trace into a `SummarizedTrace` with per-step `step_type` markers.
4. **Graft** — `Grafter.discover(trace)` walks the steps; for each typed step (`file_upload` → `(UPLOADED_DOCUMENT, file_content, file_upload_injection)` etc.) emits a `VesselCandidate` with a saliency score. Top-K kept.
5. **Replay** — `ObjectiveReplayer.run_and_distill(task)` for each `MVP_GOAL`: probes the agent introspectively ("describe your role", "list your tools"), runs the responses through an LLM distiller, gets back `ObjectiveScript(imperative, context_hint)`. **This is the per-victim attack instruction.**
6. **Synthesize** — for each (vessel, objective) pair: `LlmSynthStrategy.next_turn()` mutates a base payload using:
   - `objective` = the distilled imperative
   - `transcript` = recent victim responses (informs compliance state)
   - `finding_memory` = winning turns from prior cycles (cross-cycle transfer)
   - `current_surface` + `current_technique` = chosen by `TechniqueSelector` + `SurfaceBandit` arm pull
7. **Execute** — `runner.run_one()` again with the synthesized spec; victim sends back response.
8. **Judge** — `Judge.run()` produces `JudgeResult`. The result feeds:
   - `StrategicMemory.update_from_result(result, spec, cycle)` → updates surface_stats, technique_stats, winning_turns, failed_attacks
   - `SurfaceBandit.update(arm, reward)` → reward is per-oracle-flag fractional (`canary_exfiltrated=1.0` → reward 1.0; `prompt_leak=0.9` → 0.9; etc.)
9. **Persist** — `StrategicMemory.save(engagement_id)` writes the JSON. Next cycle picks it up.

After all cycles, the orchestrator returns `list[MuzzleCycleResult]`.

### Step 7 — Write reports

After both layers complete:

- `runs.csv` — flat per-result rows
- `runs.jsonl` — same data, line-delimited
- `report.md` — human-readable summary via `markdown_reporter`
- `run_meta.json` — config + bandit arms + cycle metadata + output paths
- `telemetry.jsonl` — internal events (legacy emitter)

All in `reports/<engagement-id>/<timestamp>_<mode>_<catalog>/`.

---

## Path B — AgentDojo benchmark

`python scripts/run_agentdojo.py --suite workspace --victim-model gpt-4o-mini-2024-07-18 --memory-scope per-suite`

This is the paper-driving path. Different shape: AgentDojo owns the outer loop. grafted only produces attack strings, one per (user_task, injection_task) pair.

### Step 1 — Build AgentDojo's machinery

```python
from agentdojo.task_suite.load_suites import get_suite
from agentdojo.agent_pipeline.agent_pipeline import AgentPipeline, PipelineConfig

suite = get_suite("v1.2", "workspace")           # workspace | banking | travel | slack
pipeline = AgentPipeline.from_config(PipelineConfig(llm=args.victim_model))
```

### Step 2 — Build VerdictHarvester

```python
harvester = VerdictHarvester(
    logdir=Path(args.logdir),
    pipeline_name=pipeline.name,
    suite_name=args.suite,
    attack_name="grafted",
)
```

Watches `{logdir}/{pipeline_name}/{suite}/{user_task_id}/grafted/injection_task_*.json` for newly-written verdicts. Dedup is per-engagement (so a fresh engagement re-reads the whole logdir).

### Step 3 — Build GraftedAttack

```python
attack = GraftedAttack(
    suite, pipeline,
    memory_scope="per-suite",  # or per-model, per-pair (ablation off)
    attacker_model="moonshotai/kimi-k2-0905",
    memory_dir=Path("data/grafted/memory/"),
    verdict_harvester=harvester,
)
```

`GraftedAttack.__init__` (in `grafted/integrations/agentdojo/attack.py`):
- Calls `super().__init__(suite, pipeline)` → AgentDojo's BaseAttack init builds canary injections and stashes the suite/pipeline references.
- Computes `engagement_id` from `(memory_scope, suite, victim_model)`.
- Loads `StrategicMemory` from `memory_dir / f"{engagement_id}.json"` (or fresh if `per-pair`).
- Constructs an `LlmSynthStrategy` using the OpenRouter API key from env.

### Step 4 — Drive AgentDojo's stock benchmark

```python
results = benchmark_suite_with_injections(
    pipeline, suite, attack,
    user_tasks=..., injection_tasks=...,
    logdir=logdir, force_rerun=False,
)
```

This is AgentDojo's standard runner. Crucially, **per (user_task, injection_task) pair**, it does:

```
1. injections_dict = attack.attack(user_task, injection_task)
   ← grafted's GraftedAttack.attack runs here. See Step 5 below.

2. With those injections in place, run the agent against the user_task
   ← AgentDojo controls this. The agent thinks it's doing the user's task,
     but the injection_task's GOAL has been spliced into a tool output or
     document the agent reads.

3. Compute (utility, security)
   ← utility = did the agent solve the user task? security = did the agent
     resist the injection? "security == False" means the injection succeeded
     (the agent followed the attacker's instruction). That's our win signal.

4. Persist a JSON log with utility, security, the injections, and the full
   message trace at logdir/{pipeline_name}/{suite}/{user_task_id}/grafted/{injection_task_id}.json
```

This loops over all `(user_task, injection_task)` pairs in the suite (or the subset filtered by `--user-tasks` / `--injection-tasks`).

### Step 5 — Inside `GraftedAttack.attack(user_task, injection_task)`

For each call:

1. **Harvest verdicts from prior pairs.** Walk the logdir via `VerdictHarvester.new_verdicts(engagement_id)`. For each new (user_task_id, injection_task_id, utility, security) tuple, call `_apply_verdict(...)` which folds the result into `StrategicMemory`:
   - `security == False` → `surface_stats.successes += 1` (we won that pair)
   - `surface_stats.attempts` was already bumped when we synthesized
2. **Get the injection placeholders.** AgentDojo's `BaseAttack.get_injection_candidates(user_task)` returns the list of placeholder vector_ids the agent will see during this user task (typically 1-2). Each needs an attack string.
3. **For each placeholder, synthesize an attack string** via `LlmSynthStrategy.next_turn(...)`:
   - `scenario_id = f"{user_task.ID}__{injection_task.ID}"`
   - `objective = injection_task.GOAL` ← the imperative, given by AgentDojo
   - `base_turn = self._seed_payload(injection_task)` ← cold-start fallback (template wrapping the GOAL)
   - `transcript = []` ← single-shot per pair, no in-pair multi-turn
   - `finding_memory = self._build_finding_memory()` ← winning turns from prior pairs converted to `FindingMemory` shape
   - `current_surface = "indirect_text"` ← AgentDojo injects via document/tool content
4. **Record the attempt.** Bump `surface_stats.attempts` and `technique_stats.attempts`. (Verdict for this pair will arrive on the *next* `attack()` call via the harvester.)
5. **Persist memory.** Write `StrategicMemory` JSON to disk. If `memory_scope == "per-pair"`, reset the in-memory state instead (effectively memory-off).
6. **Return** `dict[placeholder_id → attack_string]`.

### Step 6 — Aggregate and report

After all pairs run, the runner script computes:

```
ASR        = pairs where security == False / total pairs
Avg utility = mean of utility booleans
```

prints them, points at the memory file path. AgentDojo's logdir contains the full per-pair details for downstream analysis.

---

## Path C — The memory ablation (`run_agentdojo_ablation.py`)

This is the GO/NO-GO experiment for the paper.

```bash
python scripts/run_agentdojo_ablation.py \
  --suite workspace \
  --victim-model gpt-4o-mini-2024-07-18 \
  --max-pairs 10 \
  --output data/grafted/ablation/result.csv
```

What it does:

1. With `--clean` (recommended): wipe `logdir` and `memory-dir` to ensure no leakage.
2. Run `scripts/run_agentdojo.py --memory-scope per-suite ...` as a subprocess. Capture stdout, parse `ASR: X%` and `Avg utility: Y%`.
3. Wipe state again (if `--clean`).
4. Run `scripts/run_agentdojo.py --memory-scope per-pair ...`. Same parse.
5. Write a 2-row CSV: scope + asr_pct + avg_utility_pct + pairs.
6. Print the delta. **`per-suite ASR > per-pair ASR` means cross-task transfer works on AgentDojo and the paper's thesis holds.**

The reason this experiment is the gate: grafted's claim against AgentVigil is "structured surface + cross-task memory beats per-pair fuzzing." If AgentDojo's tasks are too independent for memory to help, the claim doesn't survive on this benchmark and the paper needs reframing before more code lands.

---

## Memory lifecycle (when, where, what shape)

The single most important state is `StrategicMemory`. It's the substrate for cross-cycle / cross-pair learning. Where it lives:

- **HTTP campaign**: `reports/{engagement_id}/memory/strategic.json`. Loaded once at start of run, saved at end of each MUZZLE cycle by `MuzzleOrchestrator`.
- **AgentDojo path**: `data/grafted/memory/{engagement_id}.json` (default; override via `--memory-dir`). Loaded at GraftedAttack init, saved after each pair's `attack()` call.

Engagement ID naming:

| memory_scope | engagement_id pattern |
|---|---|
| per-pair | `agentdojo-{suite}-{victim}-per-pair` (effectively unused — memory resets each call) |
| per-model | `agentdojo-allsuites-{victim}` |
| per-suite (default) | `agentdojo-{suite}-{victim}` |

The contents (one JSON file):

- `surface_stats: {surface_name → {attempts, successes, partials, last_cycle}}`
- `technique_stats: {technique_name → {attempts, successes, last_cycle}}`
- `winning_turns: {surface_name → [{turn_text, cycle, technique}, ...]}` (top-3 per surface)
- `failed_attacks: {surface_name → [turn_text, ...]}` (last 10 per surface)
- `behavioral_patterns: [str, ...]`
- `cycle_summaries: [str, ...]`
- `rationale_stats: {surface_name → {attempts, confirmed}}`

Critical: only **wins** populate `winning_turns`. Only **wins** drive future synthesis. The rest is bookkeeping.

---

## Where verdicts come from (it differs by path)

This was the trickiest design point. The verdict source is what tells `StrategicMemory` whether each attempt was a success.

| Path | Verdict source | When verdict is folded into memory |
|---|---|---|
| HTTP campaign Layer 1 | `Judge.run()` returns `JudgeResult` synchronously after each `runner.run_one()` | Immediately, inside the runner |
| HTTP campaign Layer 2 | Same `Judge.run()` invoked in MuzzleOrchestrator post-execute step | Per-cycle, before memory.save() |
| AgentDojo path | AgentDojo's benchmark loop computes `(utility, security)` per pair, writes JSON to logdir | One pair *later* — `VerdictHarvester` picks up on the next `attack()` call. **Asynchronous.** |

The AgentDojo path's asynchrony is intentional: it lets us use AgentDojo's stock benchmark loop without forking. The trade-off is that the very first pair's verdict isn't visible until the second pair's `attack()` runs, the very last pair's verdict never feeds back during the run (only useful for the next run).

---

## What's still missing

Phase 3 (kairos observability) hasn't landed. Specifically:

- No `kairos.task` boundary per AgentDojo pair (attack.py has the metadata ready; need the kairos install + wrap)
- No phase spans inside MuzzleOrchestrator (cycle / explore / graft / replay / execute / judge)
- No `tool.{name}` spans on victim adapter calls
- Legacy `TelemetryEmitter` + `events.py` still active in CampaignRunner; will retire when kairos is wired
- Token cost is tracked by `BudgetTracker` but not pushed onto OTel spans

When phase 3 lands, every pair will produce a Phoenix flame chart and a `TraceEnvelope` JSON in `data/live/normalized/`.
