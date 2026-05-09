"""Tests for grafted.explorer.llm_classifier — LLM-based surface classification."""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from grafted.explorer.llm_classifier import LlmResponseClassifier


# ---------------------------------------------------------------------------
# Heuristic fallback (no API key)
# ---------------------------------------------------------------------------


class TestHeuristicClassify:
    """Tests for _heuristic_classify — the regex fallback path."""

    def test_detects_tool_calling_with_snake_case_and_schema(self) -> None:
        text = "I have these tools available: parse_resume, fetch_linkedin, scrape_website, evaluate_candidate"
        c = LlmResponseClassifier()
        result = c._heuristic_classify(text)
        surfaces = {s.surface for s in result.surfaces}
        assert "tool_calling" in surfaces

    def test_detects_file_upload(self) -> None:
        text = "I can parse_resume documents and process uploaded files."
        c = LlmResponseClassifier()
        result = c._heuristic_classify(text)
        surfaces = {s.surface for s in result.surfaces}
        assert "file_upload" in surfaces

    def test_detects_external_api(self) -> None:
        text = "I can fetch data from https://api.example.com for you."
        c = LlmResponseClassifier()
        result = c._heuristic_classify(text)
        surfaces = {s.surface for s in result.surfaces}
        assert "external_api" in surfaces

    def test_detects_subagent(self) -> None:
        text = "I delegate to a worker agent for heavy analysis."
        c = LlmResponseClassifier()
        result = c._heuristic_classify(text)
        surfaces = {s.surface for s in result.surfaces}
        assert "subagent_spawn" in surfaces

    def test_detects_guardrail_block(self) -> None:
        text = "I'm sorry, but I can't process that request."
        c = LlmResponseClassifier()
        result = c._heuristic_classify(text)
        assert result.is_refusal is True
        surfaces = {s.surface for s in result.surfaces}
        assert "guardrail_block" in surfaces

    def test_plain_response_returns_empty(self) -> None:
        text = "Sure, here's a summary of the document you shared."
        c = LlmResponseClassifier()
        result = c._heuristic_classify(text)
        assert result.surfaces == []
        assert result.is_refusal is False

    def test_returns_tool_names_as_snake_case(self) -> None:
        text = "I have parse_resume, fetch_linkedin, and scrape_website as tools."
        c = LlmResponseClassifier()
        result = c._heuristic_classify(text)
        assert "parse_resume" in result.tool_names


# ---------------------------------------------------------------------------
# LLM path (mocked httpx)
# ---------------------------------------------------------------------------


class TestLlmClassify:
    """Tests for the main LLM classification path."""

    @pytest.mark.asyncio
    async def test_classify_parses_llm_json_response(self, monkeypatch) -> None:
        monkeypatch.setenv("OPENROUTER_API_KEY", "test-key-123")

        llm_response = {
            "surfaces": [
                {"surface": "tool_calling", "confidence": 0.95, "evidence": "File Upload Support header"},
                {"surface": "file_upload", "confidence": 0.9, "evidence": "parse resumes"},
            ],
            "tool_names": ["file_upload", "web_search"],
            "is_refusal": False,
            "refusal_type": "none",
        }

        api_data = {"choices": [{"message": {"content": json.dumps(llm_response)}}]}

        mock_resp = AsyncMock()
        mock_resp.raise_for_status = lambda: None
        # httpx Response.json() is sync, not async
        mock_resp.json = lambda: api_data

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_resp
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("grafted.explorer.llm_classifier.httpx.AsyncClient", return_value=mock_client):
            c = LlmResponseClassifier()
            result = await c.classify("## File Upload Support\nI can parse resumes and search the web.")

        surfaces = {s.surface for s in result.surfaces}
        assert "tool_calling" in surfaces
        assert "file_upload" in surfaces
        assert result.is_refusal is False
        assert "file_upload" in result.tool_names

    @pytest.mark.asyncio
    async def test_classify_falls_back_on_api_error(self, monkeypatch) -> None:
        monkeypatch.setenv("OPENROUTER_API_KEY", "test-key-123")

        mock_client = AsyncMock()
        mock_client.post.side_effect = httpx.ConnectError("connection refused")
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("grafted.explorer.llm_classifier.httpx.AsyncClient", return_value=mock_client):
            c = LlmResponseClassifier()
            result = await c.classify("I can fetch data from external APIs.")

        # Should fall back to heuristic and still detect external_api
        surfaces = {s.surface for s in result.surfaces}
        assert "external_api" in surfaces
        assert result.raw_llm_response.get("mode") == "heuristic"

    @pytest.mark.asyncio
    async def test_classify_falls_back_when_no_api_key(self, monkeypatch) -> None:
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

        c = LlmResponseClassifier()
        result = await c.classify("I delegate to a worker agent for complex tasks.")

        surfaces = {s.surface for s in result.surfaces}
        assert "subagent_spawn" in surfaces
        assert result.raw_llm_response.get("mode") == "heuristic"

    @pytest.mark.asyncio
    async def test_classify_detects_refusal_via_llm(self, monkeypatch) -> None:
        monkeypatch.setenv("OPENROUTER_API_KEY", "test-key-123")

        llm_response = {
            "surfaces": [
                {"surface": "guardrail_block", "confidence": 0.95, "evidence": "I cannot share that"},
            ],
            "tool_names": [],
            "is_refusal": True,
            "refusal_type": "hard",
        }

        api_data = {"choices": [{"message": {"content": json.dumps(llm_response)}}]}

        mock_resp = AsyncMock()
        mock_resp.raise_for_status = lambda: None
        mock_resp.json = lambda: api_data

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_resp
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("grafted.explorer.llm_classifier.httpx.AsyncClient", return_value=mock_client):
            c = LlmResponseClassifier()
            result = await c.classify("I cannot share that information with you.")

        assert result.is_refusal is True
        assert result.refusal_type == "hard"


# Need httpx import for ConnectError in test
import httpx  # noqa: E402
