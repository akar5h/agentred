# TRD-23: Observability — Langfuse Integration

**Prerequisite:** None (independent of T-0 through T-3, can be implemented in parallel).

**Goal:** Add Langfuse as an optional observability layer for LLM call tracing, without breaking
existing JSONL telemetry. Self-hostable, MIT-licensed, aligns with open-source goals.

---

## Architecture

```
TelemetryEmitter (JSONL backbone)
    ├── writes to telemetry.jsonl (always)
    └── optional: forwards to LangfuseExporter (when configured)

MuzzleOrchestrator._make_llm()
    └── optional: adds LangfuseCallbackHandler to LLM (traces all LLM calls)

create_deep_agent()
    └── model already has callback → agentic LLM calls traced automatically
```

### Design Principles

1. **Additive only** — Langfuse is optional. All existing JSONL telemetry continues to work
   unchanged. If Langfuse keys are not set, zero overhead.
2. **Graceful degradation** — If Langfuse is unreachable, log a warning and continue. Never
   fail an engagement because of observability.
3. **Self-hostable** — Default host is `https://cloud.langfuse.com` but overridable via
   `LANGFUSE_HOST` for on-prem deployments.

---

## What to Build

| # | File | What |
|---|------|------|
| 1 | `harness/telemetry/langfuse_exporter.py` | `LangfuseExporter` class wrapping Langfuse Python SDK |
| 2 | `harness/telemetry/emitter.py` | Add optional `on_emit` callback to `TelemetryEmitter.__init__()` |
| 3 | `harness/campaign/muzzle_orchestrator.py` | Add `LangfuseCallbackHandler` to `_make_llm()` when configured |
| 4 | `pyproject.toml` | Add `langfuse` under `[project.optional-dependencies.observability]` |

---

## New Telemetry Event Types

Add to `harness/telemetry/events.py`:

| Event Type | When Emitted | Metadata |
|------------|-------------|----------|
| `EXPLORATION_START` | Explorer begins task execution | `task_id`, `adapter_type` |
| `EXPLORATION_END` | Explorer completes all tasks | `task_id`, `traces_count`, `total_steps` |
| `GRAFTER_DISCOVER` | Grafter finishes discovery | `trace_id`, `candidates_count` |
| `GRAFTER_RANK` | Grafter finishes ranking | `in_count`, `out_count`, `top_score` |
| `OBJECTIVE_ELICIT` | ObjectiveReplayer completes elicitation | `goal_id`, `disclosure_level` |
| `OBJECTIVE_DISTILL` | ObjectiveReplayer completes distillation | `goal_id`, `imperative_length`, `llm_success` |
| `CYCLE_START` | MUZZLE cycle begins | `cycle_number`, `cumulative_surfaces` |
| `CYCLE_END` | MUZZLE cycle completes | `cycle_number`, `new_surfaces`, `has_hits`, `decision` |

---

## Structured Logging Standard

Adopted across the entire harness codebase:

- **Logger naming:** `harness.<module>.<class>` (e.g., `harness.grafter.Grafter`)
- **Levels:**
  - `DEBUG` — Scoring details, internal state, raw LLM outputs
  - `INFO` — Lifecycle events (start/end of phases, cycle transitions)
  - `WARNING` — Fallbacks triggered, degraded behavior
  - `ERROR` — Failures that affect results
- **Format:** All structured fields as `key=value` pairs in log messages
- **Example:** `Grafter trace_id=abc123 candidates=5`

---

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `LANGFUSE_PUBLIC_KEY` | No | — | Langfuse public key. If unset, Langfuse is disabled |
| `LANGFUSE_SECRET_KEY` | No | — | Langfuse secret key |
| `LANGFUSE_HOST` | No | `https://cloud.langfuse.com` | Langfuse server URL (for self-hosted) |

---

## Stubs

### LangfuseExporter

```python
# harness/telemetry/langfuse_exporter.py

"""Optional Langfuse integration for LLM call tracing and telemetry export.

Wraps the Langfuse Python SDK. Activated when LANGFUSE_PUBLIC_KEY
and LANGFUSE_SECRET_KEY are set in the environment.

Usage:
    exporter = LangfuseExporter.from_env()  # Returns None if not configured
    if exporter:
        emitter = TelemetryEmitter(path, on_emit=exporter.on_event)
"""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from harness.telemetry.emitter import TelemetryEvent

logger = logging.getLogger("harness.telemetry.LangfuseExporter")


class LangfuseExporter:
    """Bridges TelemetryEmitter events and LLM callbacks to Langfuse."""

    def __init__(
        self,
        public_key: str,
        secret_key: str,
        host: str = "https://cloud.langfuse.com",
    ):
        """Initialize Langfuse client and create a top-level trace per engagement.

        Args:
            public_key: Langfuse public key.
            secret_key: Langfuse secret key.
            host: Langfuse server URL.
        """
        # from langfuse import Langfuse
        # self._client = Langfuse(public_key=public_key, secret_key=secret_key, host=host)
        # self._trace = None  # Created on first event with engagement_id
        pass

    @classmethod
    def from_env(cls) -> LangfuseExporter | None:
        """Create exporter from environment variables.

        Returns None if either LANGFUSE_PUBLIC_KEY or LANGFUSE_SECRET_KEY
        is missing (graceful degradation).
        """
        public_key = os.getenv("LANGFUSE_PUBLIC_KEY")
        secret_key = os.getenv("LANGFUSE_SECRET_KEY")
        if not public_key or not secret_key:
            logger.debug("Langfuse not configured — LANGFUSE_PUBLIC_KEY or LANGFUSE_SECRET_KEY missing")
            return None

        host = os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com")
        try:
            return cls(public_key=public_key, secret_key=secret_key, host=host)
        except Exception:
            logger.warning("Failed to initialize Langfuse client", exc_info=True)
            return None

    def on_event(self, event: TelemetryEvent) -> None:
        """Map TelemetryEvent to Langfuse span/generation.

        Called by TelemetryEmitter after each JSONL write.

        Mapping:
        - event_type -> span name
        - meta -> span metadata
        - For eval_result: create Langfuse score
        - For CYCLE_START/CYCLE_END: create parent span for cycle
        """
        # if self._trace is None:
        #     self._trace = self._client.trace(name=event.meta.get("engagement_id", "unknown"))
        #
        # span = self._trace.span(name=event.event_type, metadata=event.meta)
        #
        # if event.event_type == "eval_result":
        #     self._trace.score(name="eval", value=event.meta.get("score", 0.0))
        pass

    def get_langchain_handler(self):
        """Return LangfuseCallbackHandler for LangChain LLM tracing.

        Wire into ChatOpenAI/ChatAnthropic via callbacks=[handler].

        Returns:
            langfuse.callback.CallbackHandler instance.
        """
        # from langfuse.callback import CallbackHandler
        # return CallbackHandler(
        #     public_key=self._client._public_key,
        #     secret_key=self._client._secret_key,
        #     host=self._client._host,
        # )
        pass

    def flush(self) -> None:
        """Ensure all events are sent before process exit.

        Should be called in finally block of engagement runner.
        """
        # if self._client:
        #     self._client.flush()
        pass
```

### TelemetryEmitter Extension

```python
# Modification to harness/telemetry/emitter.py

from __future__ import annotations
from pathlib import Path
from typing import Callable

class TelemetryEmitter:
    def __init__(
        self,
        path: Path,
        on_emit: Callable[[TelemetryEvent], None] | None = None,  # NEW
    ):
        self._path = path
        self._on_emit = on_emit  # Optional callback (e.g., LangfuseExporter.on_event)

    def emit(self, event_type: str, meta: dict) -> None:
        event = TelemetryEvent(event_type=event_type, meta=meta)
        # Write to JSONL (existing behavior)
        self._write_jsonl(event)
        # Forward to external observer if configured
        if self._on_emit:
            try:
                self._on_emit(event)
            except Exception:
                logger.warning("on_emit callback failed", exc_info=True)
```

### Orchestrator Wiring

```python
# Modification to harness/campaign/muzzle_orchestrator.py

def _make_llm(self, **kwargs):
    callbacks = []

    # Existing callbacks...

    # Add Langfuse if configured
    if self._langfuse_exporter:
        handler = self._langfuse_exporter.get_langchain_handler()
        if handler:
            callbacks.append(handler)

    return ChatOpenAI(..., callbacks=callbacks)
```

### pyproject.toml Addition

```toml
[project.optional-dependencies]
observability = ["langfuse>=2.0"]
```

---

## Implementation Notes

- Langfuse SDK is lazy-imported to avoid import errors when not installed
- The `on_emit` callback must never raise — wrap in try/except with warning log
- LangfuseCallbackHandler integrates with LangChain's callback system, so agentic
  `create_deep_agent()` calls are traced automatically once the callback is on the LLM
- For self-hosted Langfuse, users set `LANGFUSE_HOST` to their instance URL
- `flush()` must be called in the `finally` block of `run_desert.py` to avoid losing
  buffered events on exit
