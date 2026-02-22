# agentred

An open-source, agent-agnostic AI red-teaming harness implementing the [MUZZLE](https://arxiv.org/abs/2602.09222) iterative attack loop.

Built on [DeepAgents](https://github.com/langchain-ai/deepagents). Attacks any AI agent — HTTP API, LangGraph agent, or browser UI — without modifying the victim.

## What it does

- **Explores** the victim with benign tasks to map which attack surfaces it exposes
- **Grafts** discovered surfaces into ranked attack vessel candidates
- **Replays** the victim's own disclosures to distill precise adversarial objectives
- **Executes** a two-layer campaign: pre-engineered catalog first, LLM-adaptive gap synthesis second
- **Remembers** findings across cycles to converge on high-confidence attack vectors

## Status

TRDs (Technical Requirements Documents) complete. Implementation in progress.

See [`docs/TRD/`](docs/TRD/) for the full specification.

## License

Apache 2.0 — see [LICENSE](LICENSE).
