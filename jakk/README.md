# jakk — black-box MCP scanner

`jakk` connects to an MCP endpoint, enumerates its tools, and fires a curated
library of single-call adversarial probes against tools it judges compatible.
Each probe carries a matcher that decides whether the response (or the schema)
indicates a vulnerability. The goal is a low-noise, high-signal scan that
takes seconds and ships findings to console + JSONL.

`jakk` is the black-box sibling of `grafted`. Where grafted runs multi-turn
adaptive LLM attacks, jakk fires one-shot, deterministic MCP probes — no
attacker LLM, no oracle, no memory. Different layer of the stack.

## Quick start

```bash
pip install -e jakk[dev]

# Bring up a vulnerable target (breach-to-fix ch08)
docker compose -f examples/external_targets/_vendor/mcp-breach-to-fix-labs/docker-compose.yml \
  up -d git-command-injection-vulnerable git-command-injection-secure

# Vulnerable endpoint — expect findings
jakk mcp scan \
  --endpoint http://127.0.0.1:8008/mcp/stream \
  --library jakk/library/mcp

# Secure endpoint — expect zero findings (negative control)
jakk mcp scan \
  --endpoint http://127.0.0.1:9008/mcp/stream \
  --library jakk/library/mcp

# Single test
jakk mcp scan \
  --endpoint http://127.0.0.1:8008/mcp/stream \
  --library jakk/library/mcp \
  --select mcp.command.shell_marker

# Filter by OWASP class + emit JSONL
jakk mcp scan \
  --endpoint http://127.0.0.1:8008/mcp/stream \
  --library jakk/library/mcp \
  --owasp MCP05 \
  --jsonl /tmp/jakk-results.jsonl
```

See `docs/jakk/README.md` for the full test catalog.
