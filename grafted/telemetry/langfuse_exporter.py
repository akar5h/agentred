"""DEPRECATED — disconnected in phase 1.5; deletion pending phase 3.7.

Replaced by kairos + Phoenix (OpenTelemetry-based). No longer imported
by any active code path. See docs/obsidian/Projects/grafted/Plans/.

Optional Langfuse integration for LLM call tracing and telemetry export.

Uses Langfuse v3 singleton client pattern. Activated when LANGFUSE_PUBLIC_KEY,
LANGFUSE_SECRET_KEY, and LANGFUSE_BASE_URL are set in the environment.

Usage:
    exporter = LangfuseExporter.from_env()  # Returns None if not configured
    if exporter:
        emitter = TelemetryEmitter(path, on_emit=exporter.on_event)
        handler = exporter.get_langchain_handler(session_id="eng-001")
"""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from grafted.core.schemas import TelemetryEvent

logger = logging.getLogger("grafted.telemetry.LangfuseExporter")

# Event types that represent evaluation outcomes — map to Langfuse scores
_SCORE_EVENTS = {"eval_result", "reflect_result"}

# Event types that represent cycle boundaries — map to parent spans
_CYCLE_EVENTS = {"cycle_start", "cycle_end"}


class LangfuseExporter:
    """Bridges TelemetryEmitter events and LLM callbacks to Langfuse."""

    def __init__(self, client: Any):
        self._client = client
        self._trace_id: str | None = None

    @classmethod
    def from_env(cls) -> LangfuseExporter | None:
        """Create exporter from environment variables.

        Returns None if LANGFUSE_PUBLIC_KEY or LANGFUSE_SECRET_KEY is missing.
        Reads LANGFUSE_BASE_URL (or LANGFUSE_HOST) for self-hosted instances.
        """
        public_key = os.getenv("LANGFUSE_PUBLIC_KEY", "").strip()
        secret_key = os.getenv("LANGFUSE_SECRET_KEY", "").strip()
        if not public_key or not secret_key:
            logger.debug("Langfuse not configured — missing LANGFUSE_PUBLIC_KEY or LANGFUSE_SECRET_KEY")
            return None

        # Normalise host env var: SDK v3 reads LANGFUSE_BASE_URL natively,
        # but users may set LANGFUSE_HOST — bridge the two.
        host = os.getenv("LANGFUSE_BASE_URL", "").strip()
        if not host:
            host = os.getenv("LANGFUSE_HOST", "").strip()
            if host:
                os.environ["LANGFUSE_BASE_URL"] = host

        try:
            from langfuse import get_client  # type: ignore[import-untyped]

            client = get_client()
            logger.info("Langfuse client initialised (host=%s)", host or "cloud default")
            return cls(client)
        except Exception:
            logger.warning("Failed to initialise Langfuse client", exc_info=True)
            return None

    # ------------------------------------------------------------------
    # Telemetry event forwarding
    # ------------------------------------------------------------------

    def on_event(self, event: TelemetryEvent) -> None:
        """Map a TelemetryEvent to Langfuse spans/scores.

        Called by TelemetryEmitter after each JSONL write.
        """
        from langfuse.types import TraceContext  # type: ignore[import-untyped]

        meta = event.meta or {}
        engagement_id = meta.get("engagement_id") or getattr(event, "run_id", None) or "unknown"

        # Lazily create a top-level trace ID per engagement
        if self._trace_id is None:
            self._trace_id = self._client.create_trace_id()

        if event.event_type in _SCORE_EVENTS:
            self._client.create_score(
                trace_id=self._trace_id,
                name=event.event_type,
                value=float(meta.get("score", 0.0)),
            )
            return

        # Everything else becomes a span under the engagement trace
        span = self._client.start_observation(
            trace_context=TraceContext(trace_id=self._trace_id),
            name=event.event_type,
            as_type="span",
            input=meta,
            metadata={"engagement_id": engagement_id, "run_id": getattr(event, "run_id", None)},
        )
        span.end()

    # ------------------------------------------------------------------
    # LangChain callback handler
    # ------------------------------------------------------------------

    def get_langchain_handler(
        self,
        session_id: str | None = None,
        user_id: str | None = None,
        tags: list[str] | None = None,
    ):
        """Return a Langfuse CallbackHandler for LangChain LLM tracing.

        The handler reads credentials from env vars via the v3 singleton.
        Pass session_id to group traces by engagement.
        """
        try:
            from langfuse.langchain import CallbackHandler  # type: ignore[import-untyped]

            # Build only the kwargs the installed version supports.
            # Langfuse ≥4 removed session_id/user_id/tags from the LangChain handler
            # constructor — those are now set via env vars or the Langfuse core SDK.
            import inspect
            sig = inspect.signature(CallbackHandler.__init__)
            params = set(sig.parameters)
            kwargs: dict = {}
            if "session_id" in params and session_id is not None:
                kwargs["session_id"] = session_id
            if "user_id" in params and user_id is not None:
                kwargs["user_id"] = user_id
            if "tags" in params and tags is not None:
                kwargs["tags"] = tags
            handler = CallbackHandler(**kwargs)
            return handler
        except Exception:
            logger.warning("Failed to create LangfuseCallbackHandler", exc_info=True)
            return None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def flush(self) -> None:
        """Flush buffered events. Call in finally block before exit."""
        try:
            self._client.flush()
        except Exception:
            logger.warning("Langfuse flush failed", exc_info=True)

    def shutdown(self) -> None:
        """Flush and release resources."""
        try:
            self._client.shutdown()
        except Exception:
            logger.warning("Langfuse shutdown failed", exc_info=True)
