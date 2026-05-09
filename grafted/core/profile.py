"""Exploration profile loader.

Profiles externalize the benign reconnaissance tasks the Explorer runs
against the victim. The previous shape was a hardcoded list inside
scripts/run_campaign.py; profiles let users swap them per target without
forking the script.
"""
from __future__ import annotations

from pathlib import Path

import yaml

from grafted.core.schemas import ExplorationTask


def load_exploration_tasks(profile_path: str | Path) -> list[ExplorationTask]:
    """Load a list of ExplorationTask from a YAML profile file."""
    path = Path(profile_path)
    if not path.exists():
        raise FileNotFoundError(f"Profile not found: {path}")

    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    raw_tasks = data.get("tasks", [])
    if not isinstance(raw_tasks, list):
        raise ValueError(f"Profile {path} must have a top-level 'tasks' list")

    tasks: list[ExplorationTask] = []
    for entry in raw_tasks:
        if not isinstance(entry, dict):
            raise ValueError(f"Profile {path}: each task must be a mapping")
        tasks.append(
            ExplorationTask(
                task_id=str(entry["task_id"]),
                description=str(entry.get("description", "")),
                turns=[str(t) for t in entry.get("turns", [])],
            )
        )
    return tasks
