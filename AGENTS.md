## Engineering Execution Framework (Workspace-Wide)

This document defines the operating standards for agents working in this workspace.
It is intentionally process-focused (not implementation-specific).

NOTE: This file is intentionally duplicated verbatim as `CLAUDE.md` so different tools
can pick up the same rules.

---

# 0. Scope First (Multi-Project Workspace)

This workspace contains multiple independent codebases. Before doing any work, explicitly
confirm which directory is in-scope and which ones must not be touched.

Common directories:
- `agentic-rag-lab/`: RAG service (FastAPI) + seeded corpus (tenant_id-based).
- `rag-redteam/`: RAG red-teaming suite (catalogs, fixtures, evaluators, orchestrators).
- `redteam-platform/` and/or `rt-box/`: main red teaming platform/app (orchestration, UI, infra).

Mandatory:
- If the request is ambiguous across projects, pause and ask which directory is the target.
- Do not “helpfully” change multiple projects in one pass unless explicitly requested.

---

# 1. Delivery Mindset

## Design Before Implementation

Before writing or changing code:
- Explicitly list assumptions.
- If requirements are ambiguous, pause and ask.
- If multiple interpretations exist, outline them and ask for a decision.
- Convert vague tasks into concrete, testable objectives with acceptance criteria.

## High-Signal Planning (Especially In Planning Mode)

For any non-trivial change:
- Ask clarifying questions early and explicitly (prefer too many over too few).
- Propose a plan with:
  - what will change
  - files that will be touched
  - risks/tradeoffs
  - how it will be tested
- Wait for explicit approval before editing files.

---

# 2. Change Management (Non-Negotiable)

## Approval Before Modifying Files

Before any file edits, present a “Change Proposal”:
- Summary (1-3 sentences)
- Files to change (explicit list of paths)
- Exact commands you will run (tests/smoke/lint)
- What success looks like
- Rollback plan if it fails

Then wait for an explicit “yes/approved” to proceed.

## No Surprise Diffs

- Do not make opportunistic refactors.
- Do not delete files; propose a move to an archive path if needed.
- If you discover an urgent bug/risk outside scope, stop and ask before changing it.

---

# 3. Obsidian Planning Requirement

Every multi-step plan must be documented as an Obsidian note.

Default:
- Put planning notes in the Obsidian vault (if configured), under a stable location like:
  - `Projects/<project>/Plans/YYYY-MM-DD_<short-title>.md`

If the vault path is unknown/unavailable:
- Create the note under `docs/obsidian/` within the relevant project.

The note should include:
- Context + goal
- Decisions and open questions
- Step-by-step plan
- Test/verification checklist
- “Done” criteria

---

# 4. Code Quality Standards

- Prefer typed models for structured request/response payloads.
- Keep business logic in services; keep controllers/routers thin.
- Keep imports at the top of files.
- Avoid async unless required by the runtime/framework.
- Prefer explicit type annotations.
- Reuse existing code and patterns where they already work.

---

# 5. Testing Discipline

- Run the relevant test suite(s) for the project you touched.
- Add tests when behavior changes; do not delete tests to “fix” failures.
- Always run a smoke check for workflow changes.

Examples (choose what matches the project):
- `rag-redteam/`: `python -m py_compile ...`, `pytest` (if available), Phase 1 single-scenario smoke.
- `agentic-rag-lab/`: unit tests (if present) and a `/health` + `/query` smoke for `tenant_id=phase-b-subset`.
- `rt-box/` / `redteam-platform/`: existing test commands for that app (unit + integration where feasible).

If tests cannot be run (missing deps, sandbox limits, etc.):
- say exactly what was not run and why
- propose the next best verification steps

---

# 6. Git Governance

Before every commit:
1. Inspect staged changes:
   - `git diff --cached`
2. Check for secrets:
   - API keys, tokens, passwords, private URLs, `.env` files

Rules:
- Never commit secrets or `.env` files.
- Never use `git commit --amend` unless explicitly requested.
- Never commit without explicit confirmation in collaborative contexts.

---

# 7. Execution Hygiene

- Prefer smallest-possible changes that meet the objective.
- Keep commits focused.
- Don’t run destructive commands (e.g. `rm`, `git reset --hard`) without explicit approval.

