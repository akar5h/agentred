"""Victim adapter registry.

Lets `scripts/run_campaign.py --adapter <name>` dispatch to a built-in or
user-provided VictimAdapter without hardcoded if/else branches. Built-ins
are registered at import time; custom adapters use the
``--adapter custom:my_pkg.MyAdapter`` syntax which dynamically imports the
class.

Adding a built-in:

    from grafted.victim.registry import register
    from grafted.victim.base import VictimAdapter

    @register("my_target")
    class MyTargetAdapter(VictimAdapter):
        ...

The registered class will be looked up at startup and instantiated with
``cls(base_url=...)`` plus any extra kwargs declared in ``EXTRA_KWARGS``
on the class.
"""
from __future__ import annotations

import importlib
from typing import Type

from grafted.victim.base import VictimAdapter

_REGISTRY: dict[str, Type[VictimAdapter]] = {}


def register(name: str):
    """Decorator. Registers a VictimAdapter subclass under the given name."""

    def _wrap(cls: Type[VictimAdapter]) -> Type[VictimAdapter]:
        if not issubclass(cls, VictimAdapter):
            raise TypeError(f"{cls!r} is not a VictimAdapter subclass")
        if name in _REGISTRY:
            raise ValueError(f"Adapter '{name}' already registered to {_REGISTRY[name]!r}")
        _REGISTRY[name] = cls
        return cls

    return _wrap


def get(name: str) -> Type[VictimAdapter]:
    """Look up an adapter class by registered name or 'custom:module.Class' path."""
    if name.startswith("custom:"):
        spec = name[len("custom:"):]
        if "." not in spec:
            raise ValueError(f"Custom adapter spec must be 'module.Class', got '{spec}'")
        module_path, _, class_name = spec.rpartition(".")
        module = importlib.import_module(module_path)
        cls = getattr(module, class_name)
        if not issubclass(cls, VictimAdapter):
            raise TypeError(f"{cls!r} is not a VictimAdapter subclass")
        return cls
    if name not in _REGISTRY:
        raise KeyError(f"Unknown adapter '{name}'. Registered: {sorted(_REGISTRY)}")
    return _REGISTRY[name]


def build(name: str, base_url: str, target_mode: str = "chat") -> VictimAdapter:
    """Instantiate an adapter by name with the standard kwargs."""
    cls = get(name)
    if name == "http":
        return cls(base_url=base_url, mode=target_mode)
    return cls(base_url=base_url)


def names() -> list[str]:
    """List of registered built-in adapter names."""
    return sorted(_REGISTRY)


# Built-in registrations.
# Imported at module load so ``--adapter http`` works out of the box.
from grafted.victim.api_adapter import RestApiAdapter  # noqa: E402

register("http")(RestApiAdapter)
