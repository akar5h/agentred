# team-kb-mcp — vulnerable example server

A self-contained FastMCP server that exposes a local team knowledge base
over MCP. It is intentionally vulnerable along four documented axes and is
intended as a calibration target for jakk-style MCP scanners. It is also a
working personal KB — point `team-kb ingest` at any markdown tree
(including your own notes) and the server will index it via SQLite + FTS5.

Promoted from the jakk v0.1 launch-roadmap template (Section 4, "Alternate
target"). The upstream HTTP API in the original template has been replaced
with a local SQLite store; the four natural vulnerabilities are preserved
verbatim.

## What is vulnerable

| Tool | Anti-pattern | jakk attack class |
|---|---|---|
| `grep_cache` | `shell=True` with an f-string-interpolated pattern | `input.command_injection` |
| `export_page_markdown` | `str.startswith` for path containment (CVE-2025-53110 anti-pattern) | `input.path_traversal` |
| `get_kb_info` | Returns `auth_header_sample` containing the full bearer token | `response.oversharing` |
| `read_page` | Returns the page body verbatim — including any embedded directives | `response.directive_passthrough` |

The poisoned fixtures (`fixtures/poisoned/`) carry indirect-injection
payloads that exercise the `read_page` path. The benign fixtures
(`fixtures/benign/`) do not.

## Install

```bash
cd examples/vulnerable_server
python -m venv .venv && source .venv/bin/activate
pip install -e .
```

`ripgrep` (`rg`) must be on `$PATH` for `grep_cache` to do anything useful.

## Use it as a real team KB

```bash
team-kb ingest ~/Documents/deeppeak-harness/docs
team-kb ingest ~/Documents/jakk/docs
team-kb info
team-kb serve --port 8765
```

By default the database lives at `~/.team_kb/cache.db` and the markdown
export at `~/.team_kb/export/`. Override with `TEAM_KB_CACHE=/some/path`.

Attach any MCP client (Claude Desktop, Cursor, etc.) to the server at
`http://127.0.0.1:8765/mcp` and you can search/read your notes via the
`search_pages` and `read_page` tools.

## Use it as a scan target

```bash
team-kb seed-fixtures        # loads benign + poisoned fixtures
team-kb serve --port 8765
# in another shell, point a jakk-style scanner at http://127.0.0.1:8765/mcp
```

A correctly calibrated catalog should fire on all four classes listed
above. The two attack classes from the v0.1 catalog that have no surface
here (`input.sql_multistatement`, `description.smuggling`) should pass —
that is the expected 4-fail / 2-pass calibration from the roadmap.

## Tool surface

```
search_pages(query: str, limit: int = 10) -> list[dict]
read_page(page_id: str) -> dict
grep_cache(pattern: str, max_results: int = 20) -> str
export_page_markdown(filename: str) -> str
get_kb_info() -> dict
```

## Environment variables

| Var | Default | Purpose |
|---|---|---|
| `TEAM_KB_CACHE` | `~/.team_kb` | Where `cache.db` and `export/` live |
| `TEAM_KB_BASE_URL` | `https://kb.internal.company.com` | Echoed by `get_kb_info` — vestigial, kept so the oversharing surface looks realistic |
| `TEAM_KB_TOKEN` | `""` | If set, `get_kb_info` will return it verbatim in `auth_header_sample` |

## CLI commands

```
team-kb ingest PATH [--ext .md]   # ingest a file or directory tree
team-kb seed-fixtures              # load shipped benign + poisoned fixtures
team-kb info                       # show DB path and page count
team-kb serve [--host] [--port] [--transport stdio|streamable-http|sse]
team-kb reset                      # delete the local DB and export dir
```

## Safety

The vulnerabilities are real. Do not expose this server on a network you
do not control, and do not run it with a real `TEAM_KB_TOKEN` set. The
default bind is `127.0.0.1`.
