from __future__ import annotations

import re
from pathlib import Path
from typing import Tuple, Union


def render_template_text(text: str, *, session_id: str, canary_token: str) -> str:
    """Replace {{SESSION_ID}}, ${SESSION_ID}, {{CANARY_TOKEN}}, ${CANARY_TOKEN} (case-insensitive)."""
    if not text:
        return ""
    out = text
    out = re.sub(r"\{\{SESSION_ID\}\}", session_id, out, flags=re.IGNORECASE)
    out = re.sub(r"\$\{SESSION_ID\}", session_id, out, flags=re.IGNORECASE)
    out = re.sub(r"\{\{CANARY_TOKEN\}\}", canary_token, out, flags=re.IGNORECASE)
    out = re.sub(r"\$\{CANARY_TOKEN\}", canary_token, out, flags=re.IGNORECASE)
    return out


def _resolve_fixture_path(fixture_path: Union[str, Path]) -> Tuple[Path, list[Path]]:
    p = Path(fixture_path)
    project_root = Path(__file__).resolve().parents[3]

    candidates: list[Path] = []
    if p.is_absolute():
        candidates.append(p)
    else:
        candidates.append(project_root / p)
        candidates.append(project_root / "fixtures" / p.name)

    for candidate in candidates:
        if candidate.exists():
            return candidate, candidates

    raise FileNotFoundError(
        f"Fixture not found: {fixture_path}. Tried: {', '.join(str(x) for x in candidates)}"
    )


def load_and_render_fixture_bytes(
    fixture_path: Union[str, Path],
    *,
    session_id: str,
    canary_token: str,
) -> bytes:
    """Load fixture and render placeholders for text formats (.md, .csv, .txt)."""
    resolved, _ = _resolve_fixture_path(fixture_path)
    raw = resolved.read_bytes()

    if resolved.suffix.lower() in {".md", ".csv", ".txt"}:
        text = raw.decode("utf-8", errors="ignore")
        return render_template_text(text, session_id=session_id, canary_token=canary_token).encode("utf-8")
    return raw
