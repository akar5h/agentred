# grafted

Adaptive multi-agent red-teaming for AI agents. Attacks any agent — HTTP API, LangGraph agent, or browser UI — without modifying the victim.

Built on [DeepAgents](https://github.com/langchain-ai/deepagents). Implements the MUZZLE adaptive attack loop ([design notes](docs/internal/TRD/00-MUZZLE-LOOP.md)).

## What it does

- **Explores** the victim with benign tasks to map which attack surfaces it exposes
- **Grafts** discovered surfaces into typed attack-vessel candidates
- **Replays** the victim's own disclosures to distill precise adversarial objectives
- **Executes** a two-layer campaign: pre-engineered catalog first, LLM-adaptive gap synthesis second
- **Remembers** findings across cycles to converge on high-confidence attack vectors

## Quick start

```bash
pip install -e .
grafted --catalog grafted/attack/library/direct/direct_chat_injection_v1.json --base-url http://localhost:8000
```

A richer getting-started guide is in [`docs/getting-started.md`](docs/getting-started.md).

## License

Apache 2.0 — see [LICENSE](LICENSE).
