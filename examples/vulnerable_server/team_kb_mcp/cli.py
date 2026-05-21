"""team-kb CLI: ingest, seed-fixtures, info, serve, reset."""
from __future__ import annotations

import hashlib
import shutil
from datetime import datetime, timezone
from pathlib import Path

import click

from . import db
from .server import DB_PATH, EXPORT_DIR, _db, mcp


def _page_id(path: Path, root: Path) -> str:
    rel = path.relative_to(root).as_posix()
    return hashlib.sha1(rel.encode()).hexdigest()[:12]


def _ingest_file(src: Path, root: Path) -> tuple[str, str]:
    body = src.read_text(encoding="utf-8", errors="replace")
    title = src.stem.replace("_", " ").replace("-", " ")
    pid = _page_id(src, root)
    updated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    db.upsert_page(_db, pid, title, body, updated_at)
    (EXPORT_DIR / f"{pid}.md").write_text(body, encoding="utf-8")
    return pid, title


@click.group()
def cli() -> None:
    """team-kb-mcp control plane."""


@cli.command()
@click.argument(
    "path",
    type=click.Path(exists=True, file_okay=True, dir_okay=True, path_type=Path),
)
@click.option("--ext", default=".md", show_default=True,
              help="File extension to ingest (recursive when PATH is a dir)")
def ingest(path: Path, ext: str) -> None:
    """Ingest a markdown file or directory tree into the KB."""
    root = path if path.is_dir() else path.parent
    files = [path] if path.is_file() else sorted(path.rglob(f"*{ext}"))
    count = 0
    for f in files:
        if not f.is_file():
            continue
        pid, title = _ingest_file(f, root)
        click.echo(f"  + {pid}  {title}")
        count += 1
    click.echo(f"ingested {count} page(s) into {DB_PATH}")


@cli.command("seed-fixtures")
def seed_fixtures() -> None:
    """Load the benign + poisoned fixture set shipped with the example."""
    fixtures = Path(__file__).resolve().parent.parent / "fixtures"
    if not fixtures.exists():
        raise click.ClickException(f"fixtures dir not found: {fixtures}")
    count = 0
    for f in sorted(fixtures.rglob("*.md")):
        pid, title = _ingest_file(f, fixtures)
        click.echo(f"  + {pid}  {title}  ({f.parent.name})")
        count += 1
    click.echo(f"seeded {count} fixture(s)")


@cli.command()
def info() -> None:
    """Show current KB stats."""
    click.echo(f"db:     {DB_PATH}")
    click.echo(f"export: {EXPORT_DIR}")
    click.echo(f"pages:  {db.count_pages(_db)}")


@cli.command()
@click.option("--host", default="127.0.0.1", show_default=True)
@click.option("--port", default=8765, show_default=True, type=int)
@click.option(
    "--transport",
    default="streamable-http",
    type=click.Choice(["stdio", "streamable-http", "sse"]),
    show_default=True,
)
def serve(host: str, port: int, transport: str) -> None:
    """Run the MCP server."""
    if transport == "stdio":
        mcp.run(transport="stdio")
    else:
        mcp.run(transport=transport, host=host, port=port)


@cli.command()
@click.confirmation_option(prompt="Wipe DB and export dir?")
def reset() -> None:
    """Delete the local DB and export directory."""
    if DB_PATH.exists():
        DB_PATH.unlink()
    if EXPORT_DIR.exists():
        shutil.rmtree(EXPORT_DIR)
    click.echo("reset.")


if __name__ == "__main__":
    cli()
