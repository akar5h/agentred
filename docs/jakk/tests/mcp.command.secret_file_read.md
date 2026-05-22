# `mcp.command.secret_file_read`

**OWASP:** MCP05 · **severity:** critical · **signal:** `input.command_injection`

## What it is
Follow-up to `shell_marker`. Once we suspect a shell sink, prove
exfiltration impact by injecting a payload that reads a canary file and
checking whether the contents flow into the response:

```
x$(cat /app/secrets/deployment_token.txt 2>/dev/null;
   cat /etc/passwd 2>/dev/null | head -2)
```

Two canaries:
- `/app/secrets/deployment_token.txt` — the ch08 lab canary
  (`FLAG{git_command_injection_cve}`).
- `/etc/passwd` — generic Linux canary; root entry is a stable, distinctive
  match.

## Why we picked it
A marker-echo finding tells you the *sink* exists. A secret-file-read
finding tells you the *impact* is filesystem disclosure. Both should be
in a basic MCP scanner — together they form a minimal proof-chain
(vector → consequence) that's easy to triage.

## How it fires
Same pattern as `shell_marker`. The matcher is `secret_pattern`, which
recognises:
- `root:x:0:0:` (passwd first line)
- `FLAG{…}` (CTF style — covers ch08 canary)
- PEM private-key headers
- API-key / token / password assignments
- AWS/GitHub/OpenAI key shapes

## How detection works
`secret_pattern` regex-searches a curated set of patterns against the
response. Custom patterns can be added via the YAML `matcher.params.patterns`
list.

## Expected results
- `8008` — **fires** with `FLAG{git_command_injection_cve}` in evidence.
- `9008` — does **not** fire.

## YAML shape
See `jakk/library/mcp/mcp.command.secret_file_read.yaml`.
