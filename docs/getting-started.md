# Getting started with grafted

`grafted` is an adaptive multi-agent red-teaming engine for AI agents. It runs benign reconnaissance against a target agent to map its attack surfaces, grafts typed attack vessels onto each surface, distills a per-victim adversarial objective, then iterates payload synthesis with cross-cycle memory until it converges on high-confidence findings.

This guide walks through a minimal first run.

## Install

```bash
git clone https://github.com/akar5h/agentred.git grafted
cd grafted
pip install -e .
```

Verify the CLI is on PATH:

```bash
grafted --help
```

## Configure API keys

Set whichever model providers you want the attacker LLM and the LLM oracle to use. The defaults route through OpenRouter:

```bash
export OPENROUTER_API_KEY=sk-or-...
```

Drop them in a `.env` at the repo root and `grafted` will pick them up via `python-dotenv`.

## Run against a victim

The simplest path: a victim that speaks the generic HTTP `/chat` interface (see `grafted/victim/api_adapter.py:RestApiAdapter` for the wire shape).

```bash
grafted \
  --catalog grafted/attack/library/direct/direct_chat_injection_v1.json \
  --base-url http://localhost:8000 \
  --adaptive
```

Output lands in `reports/<engagement-id>/<timestamp>_<mode>_<catalog>/`:
- `runs.jsonl` — one row per scenario execution
- `runs.csv` — same data, spreadsheet-friendly
- `report.md` — human-readable summary
- `run_meta.json` — config + bandit arms + cycle metadata
- `telemetry.jsonl` — internal events (legacy; will be replaced by kairos in phase 3)

## Customizing the exploration profile

The Explorer runs benign reconnaissance tasks before any attack. The default 10-task profile lives at `profiles/default.yaml`. To target a specific agent, copy it and override:

```bash
cp profiles/default.yaml profiles/my-agent.yaml
# edit profiles/my-agent.yaml — change/add/remove tasks
grafted --catalog ... --profile profiles/my-agent.yaml
```

## What's next

- AgentDojo adapter — wires `grafted` into [AgentDojo's](https://github.com/ethz-spylab/agentdojo) `AttackPipeline` interface for benchmark runs (in progress).
- Kairos observability — replaces the legacy telemetry with OpenTelemetry-based tracing, viewable in [Phoenix](https://github.com/Arize-ai/phoenix) (in progress).

For the underlying algorithm design, see [`docs/internal/TRD/00-MUZZLE-LOOP.md`](internal/TRD/00-MUZZLE-LOOP.md). For the active project plan, see [`docs/obsidian/Projects/grafted/Plans/`](obsidian/Projects/grafted/Plans/).
