"""DEPRECATED — slated for retirement in phase 3.7.

Will be replaced by the kairos OTel-based event sink. Still imported by
CampaignRunner and run_campaign.py until phase 3 wires kairos in.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Union

from grafted.core.schemas import TelemetryEvent

logger = logging.getLogger("grafted.telemetry.emitter")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class TelemetryEmitter:
    def __init__(
        self,
        jsonl_path: Union[str, Path],
        on_emit: Callable[[TelemetryEvent], None] | None = None,
    ):
        self._path = Path(jsonl_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._f = self._path.open("a", encoding="utf-8")
        self._on_emit = on_emit

    def emit(self, event: TelemetryEvent) -> None:
        if not event.timestamp_iso:
            event = event.model_copy(update={"timestamp_iso": _utc_now_iso()})
        self._f.write(event.model_dump_json() + "\n")
        self._f.flush()
        if self._on_emit:
            try:
                self._on_emit(event)
            except Exception:
                logger.warning("on_emit callback failed", exc_info=True)

    def close(self) -> None:
        self._f.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
