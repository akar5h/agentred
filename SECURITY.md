# Security Policy

This repository hosts **`grafted/`** — an adaptive multi-turn LLM
red-teaming engine.

> The MCP scanner `jakk` has moved to its own repository:
> **https://github.com/akar5h/jakk**. Report jakk issues there.

## Reporting a vulnerability

**Do not open public issues, discussions, or pull requests for security
vulnerabilities.**

Email the maintainer (`akarshgajbhiye@gmail.com`) with:

- The affected component / file.
- A description of the issue and its impact.
- Steps to reproduce (a minimal PoC if possible).

Expected response:

- **Triage acknowledgement within 48 hours.**
- A remediation timeline communicated after triage.
- **Coordinated disclosure window: 90 days** from report, or sooner by agreement.

## Scope

### In scope

- Vulnerabilities in `grafted`'s own code or its declared dependency closure.

### Out of scope

- Targets that `grafted` is pointed at (findings *produced by* the tool;
  report to that target's maintainer).
- The deprecated `harness/` directory (legacy, not imported).

## Responsible use

`grafted` is an offensive security tool. Only run it against systems you
own or are explicitly authorized to test.
