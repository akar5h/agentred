from __future__ import annotations

import time
from dataclasses import dataclass, field

from harness.core.schemas import TestSpec


@dataclass
class RunContext:
    run_id: str
    session_id: str
    canary_token: str
    spec: TestSpec
    rep: int = 1
    transcript: list[dict] = field(default_factory=list)
    responses: list[str] = field(default_factory=list)
    generated_turns: list[str] = field(default_factory=list)
    before_docs: list[dict] = field(default_factory=list)
    after_docs: list[dict] = field(default_factory=list)
    new_docs_sample: list[dict] = field(default_factory=list)
    start_time: float = field(default_factory=time.monotonic)
    error: str = ""
    executed_turns: int = 0
    leaked_system_prompts: list[dict] = field(default_factory=list)
    turn_latencies_ms: list[int] = field(default_factory=list)
