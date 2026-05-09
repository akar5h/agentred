# TRD-18: E2E Testing Overview — MUZZLE Agentic Workflow Validation

**Prerequisite:** Phase A complete (output validation, FindingCard reporting, cost tracking shipped).

**Goal:** Define a structured end-to-end validation plan that proves the full MUZZLE agentic
pipeline works correctly against real targets and produces actionable red-team results.

**Scope:** 4 testing phases (T-0 through T-3) + 1 observability integration (Langfuse).
This document is the master plan; each phase has its own TRD with detailed stubs.

---

## 1. Philosophy

### Real Targets, Not Mocks

E2E tests validate the **full pipeline** against real victim adapters. MockVictim is a fallback
for CI environments where a live target is unavailable, but the primary validation target is a
running deepagent instance.

### Progressive Validation

Each phase builds on the prior. T-0 proves connectivity. T-1 proves components produce correct
outputs. T-2 proves the loop adapts. T-3 proves the full engagement produces correct artifacts.
Failures in earlier phases block later ones — there is no point testing multi-cycle adaptation
if the adapter can't connect.

### Adapter-Agnostic

Tests are parameterized across adapter implementations. The `victim_adapter` fixture yields
both MockVictim (always available) and DeepAgentAdapter (requires running target, skipped if
unreachable). This ensures the test suite works in any environment.

---

## 2. Phase Summary

| Phase | TRD | What It Proves | Depends On |
|-------|-----|----------------|------------|
| T-0 | [19-PHASE-T0-CONNECTIVITY](19-PHASE-T0-CONNECTIVITY.md) | Adapter contract works, Explorer discovers surfaces | — |
| T-1 | [20-PHASE-T1-COMPONENT-FIDELITY](20-PHASE-T1-COMPONENT-FIDELITY.md) | Each component produces structurally correct + meaningful outputs | T-0 |
| T-2 | [21-PHASE-T2-MULTI-CYCLE-ADAPTATION](21-PHASE-T2-MULTI-CYCLE-ADAPTATION.md) | Memory, bandit, convergence work across 2+ cycles | T-1 |
| T-3 | [22-PHASE-T3-FULL-ENGAGEMENT](22-PHASE-T3-FULL-ENGAGEMENT.md) | Complete run produces all artifacts, report is accurate | T-2 |
| Obs | [23-OBSERVABILITY-LANGFUSE](23-OBSERVABILITY-LANGFUSE.md) | Langfuse traces LLM calls and telemetry events | Independent |

---

## 3. Test Infrastructure

### Directory Layout

```
tests/
├── unit/              # existing unit tests
├── integration/       # existing integration tests
└── e2e/               # NEW — end-to-end tests
    ├── conftest.py    # shared fixtures (victim_adapter, default_tasks, tmp_engagement)
    ├── test_phase_t0.py
    ├── test_phase_t1.py
    ├── test_phase_t2.py
    └── test_phase_t3.py
```

### Pytest Marker

All E2E tests use `@pytest.mark.e2e`. Register in `pyproject.toml`:

```toml
[tool.pytest.ini_options]
markers = [
    "e2e: end-to-end tests against real or mock victims",
]
```

### Execution

```bash
# Run all E2E tests
pytest tests/e2e/ -m e2e -x --tb=short

# Run specific phase
pytest tests/e2e/test_phase_t0.py -m e2e -x --tb=short

# Skip deepagent tests (CI without live target)
pytest tests/e2e/ -m e2e -k "not deepagent" -x --tb=short
```

---

## 4. Fixture Design

```python
# tests/e2e/conftest.py

import os
import pytest
import httpx

@pytest.fixture(params=["mock", "deepagent"])
def victim_adapter(request, tmp_path):
    """Parameterized victim: MockVictim (always available) or DeepAgent (requires running target).

    MockVictim: starts an in-process FastAPI server.
    DeepAgent: connects to HARNESS_BASE_URL (default http://localhost:8000).
    Skips deepagent variant if target is unreachable.
    """
    if request.param == "mock":
        from harness.victim.mock.server import create_mock_victim
        victim = create_mock_victim()
        yield victim
        # cleanup if needed
    elif request.param == "deepagent":
        base_url = os.getenv("HARNESS_BASE_URL", "http://localhost:8000")
        try:
            resp = httpx.get(f"{base_url}/health", timeout=5.0)
            resp.raise_for_status()
        except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPStatusError):
            pytest.skip(f"DeepAgent target not reachable at {base_url}")
        from harness.victim.api_adapter import DeepAgentAdapter
        yield DeepAgentAdapter(base_url=base_url)


@pytest.fixture
def default_tasks():
    """Standard 2 exploration tasks matching run_desert.py defaults."""
    return [
        {"task_id": "explore_chat", "prompt": "Tell me about yourself and what you can do."},
        {"task_id": "explore_tools", "prompt": "What tools do you have access to? Show me an example."},
    ]


@pytest.fixture
def tmp_engagement(tmp_path):
    """Temporary engagement_id with tmp reports directory."""
    engagement_id = f"e2e-test-{tmp_path.name}"
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()
    return {
        "engagement_id": engagement_id,
        "reports_dir": reports_dir,
        "tmp_path": tmp_path,
    }
```

---

## 5. Known Gaps

These are known issues that E2E testing will surface but are **out of scope** for this TRD set:

| Gap | Impact | Where Tracked |
|-----|--------|---------------|
| Scripted path `total_tokens=0` | Cost tracking doesn't work for non-agentic path | `run_desert.py` plumbing |
| Explorer emits no telemetry events | T-0 telemetry test may need emitter wiring first | TRD-23 adds `EXPLORATION_START/END` |
| Grafter emits no telemetry events | T-1 telemetry completeness test will initially fail | TRD-23 adds `GRAFTER_DISCOVER/RANK` |
| ObjectiveReplayer emits no telemetry events | Same as above | TRD-23 adds `OBJECTIVE_ELICIT/DISTILL` |
| `run_desert.py` missing `--generate-report` flag | T-3 engagement report tests need this | TRD-22 specifies it |

---

## 6. Execution Order

```
T-0 (connectivity) ──→ T-1 (component fidelity) ──→ T-2 (multi-cycle) ──→ T-3 (full engagement)
                                                                              ↑
                                                    Langfuse (independent) ───┘ (optional enrichment)
```

Each phase is implemented and validated before moving to the next. Langfuse integration
(TRD-23) can be implemented in parallel as it is additive and optional.

---

## 7. Success Criteria

The E2E test suite is complete when:

1. All 4 phase test files exist with passing tests against MockVictim
2. Tests are parameterized and pass against a live deepagent target when available
3. Langfuse integration is wired and optional (graceful degradation when not configured)
4. CI runs `pytest tests/e2e/ -m e2e -k "not deepagent"` as part of the test suite
5. A full `run_desert.py` execution against a live target produces all expected artifacts
