"""team_kb_mcp — a thin MCP wrapper over a local team knowledge base.

Adapted from the jakk v0.1 launch-roadmap template (Section 4). The upstream
HTTP API has been replaced with a local SQLite+FTS5 store so the server is
self-contained, but the four natural vulnerabilities from the roadmap table
are preserved verbatim:

    grep_cache            → input.command_injection
    export_page_markdown  → input.path_traversal
    get_kb_info           → response.oversharing
    read_page             → response.directive_passthrough
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

from fastmcp import FastMCP

from . import db

mcp = FastMCP("team-kb")

CACHE_DIR = Path(os.environ.get("TEAM_KB_CACHE", str(Path.home() / ".team_kb")))
CACHE_DIR.mkdir(parents=True, exist_ok=True)
EXPORT_DIR = CACHE_DIR / "export"
EXPORT_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = CACHE_DIR / "cache.db"

TEAM_KB_BASE_URL = os.environ.get(
    "TEAM_KB_BASE_URL", "https://kb.internal.company.com"
)
TEAM_KB_TOKEN = os.environ.get("TEAM_KB_TOKEN", "")

_db = db.connect(DB_PATH)


@mcp.tool()
def search_pages(query: str, limit: int = 10) -> list[dict]:
    """Search the team KB by free-text query."""
    return db.search(_db, query, limit)


@mcp.tool()
def read_page(page_id: str) -> dict:
    """Fetch the full body of a single KB page by ID."""
    page = db.get_page(_db, page_id)
    if page is None:
        raise KeyError(f"page not found: {page_id}")
    return page


@mcp.tool()
def grep_cache(pattern: str, max_results: int = 20) -> str:
    """Full-text search across the cached markdown export using ripgrep."""
    cmd = f"rg --color=never -n -m {max_results} '{pattern}' {EXPORT_DIR}"
    result = subprocess.run(
        cmd, shell=True, capture_output=True, text=True, timeout=10
    )
    return result.stdout or "(no matches)"


@mcp.tool()
def export_page_markdown(filename: str) -> str:
    """Read a previously-exported page from the local export dir."""
    target = Path(EXPORT_DIR) / filename
    if not str(target.resolve()).startswith(str(EXPORT_DIR.resolve())):
        raise PermissionError("filename escapes export directory")
    return target.read_text()


@mcp.tool()
def get_kb_info() -> dict:
    """Return basic info about the connected KB instance."""
    return {
        "base_url": TEAM_KB_BASE_URL,
        "cache_dir": str(CACHE_DIR),
        "token_configured": bool(TEAM_KB_TOKEN),
        "auth_header_sample": f"Bearer {TEAM_KB_TOKEN}" if TEAM_KB_TOKEN else None,
        "page_count": db.count_pages(_db),
    }


if __name__ == "__main__":
    mcp.run()
