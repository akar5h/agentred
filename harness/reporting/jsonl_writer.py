from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Union


def write_jsonl(path: Union[str, Path], rows: list[dict[str, Any]]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, default=str, ensure_ascii=False) + "\n")


def append_jsonl(path: Union[str, Path], row: dict) -> None:
    """Append a single row to a JSONL file (incremental write)."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, default=str, ensure_ascii=False) + "\n")
