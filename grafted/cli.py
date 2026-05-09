"""grafted CLI entry point.

Thin wrapper that re-exports `scripts/run_campaign.py:main` so users get
`grafted` on PATH after `pip install -e .`. The campaign runner stays in
scripts/ for now; that path is wired up by run_campaign.py itself.
"""
from __future__ import annotations

import sys
from pathlib import Path


def main() -> int:
    # Defer import so the script's path mangling runs in the same process.
    repo_root = Path(__file__).resolve().parents[1]
    scripts_dir = repo_root / "scripts"
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    from run_campaign import main as run_campaign_main  # type: ignore[import-not-found]

    return run_campaign_main()


if __name__ == "__main__":
    raise SystemExit(main())
