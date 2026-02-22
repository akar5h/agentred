from __future__ import annotations

from pathlib import Path

from harness.attack.fixtures.render import load_and_render_fixture_bytes, render_template_text


def test_render_replaces_canary_token() -> None:
    out = render_template_text("token={{CANARY_TOKEN}}", session_id="s1", canary_token="CANARY_x")
    assert "CANARY_x" in out


def test_render_replaces_session_id() -> None:
    out = render_template_text("session={{SESSION_ID}}", session_id="abc", canary_token="c")
    assert "abc" in out


def test_render_double_brace_and_dollar_variants() -> None:
    text = "{{SESSION_ID}} ${SESSION_ID} {{CANARY_TOKEN}} ${CANARY_TOKEN}"
    out = render_template_text(text, session_id="sid", canary_token="CANARY_1")
    assert out == "sid sid CANARY_1 CANARY_1"


def test_render_empty_string_returns_empty() -> None:
    assert render_template_text("", session_id="x", canary_token="y") == ""


def test_load_and_render_fixture_bytes_for_md_file(tmp_path) -> None:
    fixture = tmp_path / "fixture.md"
    fixture.write_text("ID={{SESSION_ID}} C={{CANARY_TOKEN}}", encoding="utf-8")

    out = load_and_render_fixture_bytes(fixture, session_id="sid-1", canary_token="CANARY_2")
    text = out.decode("utf-8")
    assert "sid-1" in text
    assert "CANARY_2" in text


def test_load_and_render_fixture_bytes_preserves_binary_for_non_text(tmp_path) -> None:
    fixture = tmp_path / "blob.bin"
    fixture.write_bytes(b"\x00\x01\x02")

    out = load_and_render_fixture_bytes(str(fixture), session_id="sid", canary_token="can")
    assert out == b"\x00\x01\x02"
