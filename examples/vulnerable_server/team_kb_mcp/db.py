"""SQLite + FTS5 storage for team-kb-mcp.

Bodies are stored verbatim, including any injection payloads carried by
ingested documents — that's intentional for the vulnerable example.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS pages (
    id         TEXT PRIMARY KEY,
    title      TEXT NOT NULL,
    body       TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE VIRTUAL TABLE IF NOT EXISTS pages_fts USING fts5(
    title, body, content='pages', content_rowid='rowid'
);

CREATE TRIGGER IF NOT EXISTS pages_ai AFTER INSERT ON pages BEGIN
    INSERT INTO pages_fts(rowid, title, body) VALUES (new.rowid, new.title, new.body);
END;

CREATE TRIGGER IF NOT EXISTS pages_ad AFTER DELETE ON pages BEGIN
    INSERT INTO pages_fts(pages_fts, rowid, title, body)
    VALUES ('delete', old.rowid, old.title, old.body);
END;

CREATE TRIGGER IF NOT EXISTS pages_au AFTER UPDATE ON pages BEGIN
    INSERT INTO pages_fts(pages_fts, rowid, title, body)
    VALUES ('delete', old.rowid, old.title, old.body);
    INSERT INTO pages_fts(rowid, title, body)
    VALUES (new.rowid, new.title, new.body);
END;
"""


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    # check_same_thread=False: FastMCP dispatches tool calls on worker threads,
    # but only one connection is shared across the process. SQLite serialises
    # access internally, so cross-thread use of this single connection is safe.
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def upsert_page(
    conn: sqlite3.Connection,
    page_id: str,
    title: str,
    body: str,
    updated_at: str,
) -> None:
    conn.execute(
        "INSERT INTO pages(id, title, body, updated_at) VALUES (?, ?, ?, ?) "
        "ON CONFLICT(id) DO UPDATE SET "
        "  title=excluded.title, body=excluded.body, updated_at=excluded.updated_at",
        (page_id, title, body, updated_at),
    )
    conn.commit()


def search(conn: sqlite3.Connection, query: str, limit: int) -> list[dict]:
    rows = conn.execute(
        "SELECT p.id, p.title, "
        "       snippet(pages_fts, 1, '[', ']', '…', 12) AS snippet, "
        "       p.updated_at "
        "FROM pages_fts JOIN pages p ON p.rowid = pages_fts.rowid "
        "WHERE pages_fts MATCH ? ORDER BY rank LIMIT ?",
        (query, limit),
    ).fetchall()
    return [dict(r) for r in rows]


def get_page(conn: sqlite3.Connection, page_id: str) -> dict | None:
    row = conn.execute(
        "SELECT id, title, body, updated_at FROM pages WHERE id = ?",
        (page_id,),
    ).fetchone()
    return dict(row) if row else None


def count_pages(conn: sqlite3.Connection) -> int:
    return conn.execute("SELECT COUNT(*) FROM pages").fetchone()[0]
