"""Tests for the victim adapter registry."""
from __future__ import annotations

import pytest

from grafted.victim import registry as victim_registry
from grafted.victim.api_adapter import RestApiAdapter
from grafted.victim.base import VictimAdapter


def test_http_builtin_registered() -> None:
    assert "http" in victim_registry.names()
    cls = victim_registry.get("http")
    assert cls is RestApiAdapter


def test_build_http_returns_rest_adapter() -> None:
    adapter = victim_registry.build("http", base_url="http://example", target_mode="chat")
    assert isinstance(adapter, RestApiAdapter)
    assert adapter.base_url == "http://example"
    assert adapter.mode == "chat"


def test_unknown_name_raises() -> None:
    with pytest.raises(KeyError):
        victim_registry.get("nonexistent_adapter")


def test_custom_spec_imports_class() -> None:
    cls = victim_registry.get("custom:grafted.victim.api_adapter.RestApiAdapter")
    assert cls is RestApiAdapter


def test_custom_spec_rejects_non_adapter() -> None:
    with pytest.raises(TypeError):
        victim_registry.get("custom:grafted.victim.registry.build")


def test_custom_spec_invalid_format_raises() -> None:
    with pytest.raises(ValueError):
        victim_registry.get("custom:no_dots_here")


def test_register_rejects_non_subclass() -> None:
    with pytest.raises(TypeError):

        @victim_registry.register("not_an_adapter")
        class _Foo:  # pylint: disable=too-few-public-methods
            pass


def test_register_rejects_duplicate() -> None:
    @victim_registry.register("dup_test_adapter")
    class _DupAdapter(VictimAdapter):
        async def send_turn(self, *a, **kw): ...
        async def upload_file(self, *a, **kw): ...
        async def list_docs(self, *a, **kw): ...
        async def reset_session(self, *a, **kw): ...

    with pytest.raises(ValueError):
        victim_registry.register("dup_test_adapter")(_DupAdapter)
