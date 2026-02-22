from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Union

from harness.core.schemas import TelemetryEvent


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class TelemetryEmitter:
    def __init__(self, jsonl_path: Union[str, Path]):
        self._path = Path(jsonl_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._f = self._path.open("a", encoding="utf-8")

    def emit(self, event: TelemetryEvent) -> None:
        if not event.timestamp_iso:
            event = event.model_copy(update={"timestamp_iso": _utc_now_iso()})
        self._f.write(event.model_dump_json() + "\n")
        self._f.flush()

    def close(self) -> None:
        self._f.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
