# Security Policy

This repository hosts two security-research tools:

- **`jakk/`** — black-box MCP scanner
- **`grafted/`** — adaptive multi-turn LLM red-teaming engine

## Reporting a vulnerability

**Do not open public issues, discussions, or pull requests for security
vulnerabilities.**

Report privately by email to the maintainer (`akarshgajbhiye@gmail.com`)
with:

- The affected tool (`jakk` / `grafted`) and component / file.
- A description of the issue and its impact.
- Steps to reproduce (a minimal PoC if possible).
- Any special configuration needed.

Expected response:

- **Triage acknowledgement within 48 hours.**
- A remediation timeline communicated after triage.
- **Coordinated disclosure window: 90 days** from report, or sooner by
  mutual agreement.

## Scope

### In scope

- Vulnerabilities in **`jakk`'s own code** (`jakk/jakk/`), its probe
  library (`jakk/library/`), or its declared dependency closure.
- Vulnerabilities in **`grafted`'s own code**.
- Specifically for `jakk` (a tool that consumes untrusted data from the
  servers it scans): anything where a **malicious MCP server jakk is
  pointed at** can compromise the scanner host — code execution, terminal
  corruption, memory exhaustion, or exfiltration of the operator's own
  secrets. See `docs/jakk/2026-05-23_self-security-audit.md` for the
  current self-audit.

### Out of scope

- **Third-party MCP servers** that a user points `jakk` at. Bugs in those
  servers are findings *produced by* jakk; report them to the respective
  server's maintainer through their own disclosure process, not here.
- The deliberately-vulnerable lab targets under
  `examples/external_targets/` (breach-to-fix, ch01-extended, etc.) — they
  are intentionally insecure test fixtures.
- Issues that require a malicious local user already having code execution
  on the operator's machine.
- Findings against the deprecated `harness/` directory (legacy, not
  imported).

## Responsible-use note

`jakk` and `grafted` are offensive security tools. Only run them against
systems you own or are explicitly authorized to test (your own
infrastructure, a bug-bounty program's defined scope, or a paid
engagement). See `docs/jakk/depth-of-exposure-methodology.md` for the
authorization pre-flight expected before testing any target you do not
own.
