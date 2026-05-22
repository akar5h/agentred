# grafted + jakk

Two complementary red-teaming tools for AI agents and MCP servers.

| Tool | What it does | When to use it |
|---|---|---|
| **`grafted`** | Multi-turn, LLM-adaptive attacks. Explores the victim, discovers surfaces, runs adaptive campaigns with cross-cycle memory. | Capability-boundary attacks that need an LLM in the loop to learn from victim responses. |
| **`jakk`** | Single-call, deterministic MCP scanner. Connects to an endpoint, enumerates tools, fires a curated library of probes, classifies findings. | Fast black-box scans of MCP servers. Zero LLM cost. Bugs you can catch without an attacker LLM. |

Different layers of the stack. `jakk` findings can prime `grafted`'s
strategic memory; `grafted` finds bugs that only show up under
multi-turn adaptive pressure.

---

## grafted

Adaptive multi-agent red-teaming for AI agents. Attacks any agent —
HTTP API, LangGraph agent, or browser UI — without modifying the
victim. Built on [DeepAgents](https://github.com/langchain-ai/deepagents).
Implements the MUZZLE adaptive attack loop
([design notes](docs/internal/TRD/00-MUZZLE-LOOP.md)).

- **Explores** the victim with benign tasks to map which attack surfaces it exposes
- **Grafts** discovered surfaces into typed attack-vessel candidates
- **Replays** the victim's own disclosures to distill precise adversarial objectives
- **Executes** a two-layer campaign: pre-engineered catalog first, LLM-adaptive gap synthesis second
- **Remembers** findings across cycles to converge on high-confidence attack vectors

```bash
pip install -e .
grafted --catalog grafted/attack/library/direct/direct_chat_injection_v1.json --base-url http://localhost:8000
```

Getting-started guide: [`docs/getting-started.md`](docs/getting-started.md).

---

## jakk

Black-box MCP scanner. 11 probes across 6 surfaces (tool_call,
tool_list, resource_list, prompt_list, auth, authz). Verified on
breach-to-fix ch01 / ch02 / ch08 (vulnerable + secure variants).

```bash
pip install -e jakk

# Scan a local MCP endpoint
jakk mcp scan --endpoint http://127.0.0.1:8008/mcp/stream --library jakk/library/mcp

# Authenticated commercial server, safe probes only
jakk mcp scan \
  --endpoint https://api.example.com/mcp/stream \
  --library jakk/library/mcp \
  --bearer "$ACCESS_TOKEN" \
  --safe
```

Probe catalog + threat models: [`docs/jakk/`](docs/jakk/). Package
docs: [`jakk/README.md`](jakk/README.md).

---

## License

Apache 2.0 — see [LICENSE](LICENSE).
