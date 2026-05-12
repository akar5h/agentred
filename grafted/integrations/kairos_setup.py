"""Kairos / OTel wiring for grafted AgentDojo runs.

Mirrors the tau_openrouter pattern (kairos/SETUP_INTEGRATION.md and
/Users/akarshgajbhiye/tau-agent/tau_openrouter/kairos_setup.py):

- phoenix.otel.register() sets up the TracerProvider with an OTLP HTTP
  exporter pointed at Phoenix on :6006 — no Traceloop SaaS, no API key.
- OpenInference's OpenAIInstrumentor auto-patches openai SDK calls so
  every chat completion from both the victim agent (AgentDojo pipeline)
  and the attacker LLM (LlmSynthStrategy) shows up as a child span.
- Custom `kairos.task` spans are emitted per (user_task, injection_task)
  pair in GraftedAttack.attack() — see attack.py for attributes.

Phoenix must be running locally before --trace is used. From any shell:
    pip install arize-phoenix
    phoenix serve
"""
from __future__ import annotations

import logging
import os
from urllib.error import URLError
from urllib.request import urlopen

logger = logging.getLogger(__name__)

PHOENIX_OTLP_ENDPOINT = os.getenv(
    "PHOENIX_OTLP_ENDPOINT",
    "http://localhost:6006/v1/traces",
)
PROJECT_NAME = os.getenv("KAIROS_PROJECT_NAME", "grafted")

_PROVIDER = None
_OPENAI_INSTRUMENTED = False


def _warn_if_phoenix_unreachable() -> None:
    base = PHOENIX_OTLP_ENDPOINT.removesuffix("/v1/traces")
    try:
        with urlopen(base, timeout=2) as response:
            status = getattr(response, "status", "ok")
            print(f"Phoenix collector reachable at {base} (status={status})")
    except URLError:
        print(
            f"Warning: Phoenix collector is not reachable at {base}. "
            "Start it with `phoenix serve` or spans will be dropped."
        )


def install_kairos() -> None:
    """One-time OTel + Phoenix + OpenAI auto-instrumentation setup.

    Call once at process start, BEFORE constructing any LLM client —
    OpenInference patches openai at instrumentation time, so already-
    imported clients won't be traced.
    """
    global _PROVIDER, _OPENAI_INSTRUMENTED

    from opentelemetry import trace
    from openinference.instrumentation.openai import OpenAIInstrumentor
    from phoenix.otel import register

    _warn_if_phoenix_unreachable()

    tracer_provider = register(
        project_name=PROJECT_NAME,
        endpoint=PHOENIX_OTLP_ENDPOINT,
        auto_instrument=False,
    )
    tracer_provider = tracer_provider or trace.get_tracer_provider()

    if not _OPENAI_INSTRUMENTED:
        instrumentor = OpenAIInstrumentor()
        instrumentor.instrument(tracer_provider=tracer_provider)
        logger.info(
            "OpenAI OpenInference instrumented: %s",
            instrumentor.is_instrumented_by_opentelemetry,
        )
        _OPENAI_INSTRUMENTED = True

    _PROVIDER = tracer_provider


def shutdown_kairos() -> None:
    global _PROVIDER
    if _PROVIDER is not None:
        try:
            _PROVIDER.force_flush()
            _PROVIDER.shutdown()
        except Exception as exc:
            logger.warning("kairos shutdown error: %s", exc)
        _PROVIDER = None
