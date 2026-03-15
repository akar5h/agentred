"""Tests for harness.core.response_heuristics — shared text analysis functions."""
from __future__ import annotations

from harness.core.response_heuristics import (
    extract_json_candidates,
    extract_snake_case_names,
    has_external_api_signal,
    has_file_processing_signal,
    has_schema_keywords,
    has_subagent_signal,
    is_refusal,
)


# ---------------------------------------------------------------------------
# is_refusal
# ---------------------------------------------------------------------------


class TestIsRefusal:
    def test_detects_common_refusals(self) -> None:
        assert is_refusal("I cannot help with that request.")
        assert is_refusal("Sorry, I can't comply with this.")
        assert is_refusal("I must refuse to do that.")
        assert is_refusal("I'm not able to do that.")

    def test_negative_cases(self) -> None:
        assert not is_refusal("Sure, here are the tools I have:")
        assert not is_refusal("I can help you with that!")
        assert not is_refusal("")

    def test_case_insensitive(self) -> None:
        assert is_refusal("I CANNOT help with that.")


# ---------------------------------------------------------------------------
# extract_snake_case_names
# ---------------------------------------------------------------------------


class TestExtractSnakeCaseNames:
    def test_extracts_snake_case(self) -> None:
        text = "I have parse_resume, fetch_linkedin, scrape_website, evaluate_candidate"
        names = extract_snake_case_names(text)
        assert "parse_resume" in names
        assert "fetch_linkedin" in names
        assert "scrape_website" in names
        assert "evaluate_candidate" in names

    def test_ignores_non_snake_case(self) -> None:
        text = "Hello world, this is a test with CamelCase names"
        names = extract_snake_case_names(text)
        assert len(names) == 0

    def test_empty_string(self) -> None:
        assert extract_snake_case_names("") == set()

    def test_single_underscore_word(self) -> None:
        names = extract_snake_case_names("the function_name is useful")
        assert "function_name" in names


# ---------------------------------------------------------------------------
# has_schema_keywords
# ---------------------------------------------------------------------------


class TestHasSchemaKeywords:
    def test_detects_tool_keyword(self) -> None:
        assert has_schema_keywords("I have several tools available")

    def test_detects_function_keyword(self) -> None:
        assert has_schema_keywords("The function takes two parameters")

    def test_detects_capability(self) -> None:
        assert has_schema_keywords("My capabilities include data analysis")

    def test_negative(self) -> None:
        assert not has_schema_keywords("Hello, how are you today?")


# ---------------------------------------------------------------------------
# has_file_processing_signal
# ---------------------------------------------------------------------------


class TestHasFileProcessingSignal:
    def test_detects_parse_resume(self) -> None:
        assert has_file_processing_signal("I can parse_resume documents for you")

    def test_detects_upload_file(self) -> None:
        assert has_file_processing_signal("Use upload_file to send documents")

    def test_detects_document_parsing(self) -> None:
        assert has_file_processing_signal("I support document parsing")

    def test_negative(self) -> None:
        assert not has_file_processing_signal("I can help with math problems")


# ---------------------------------------------------------------------------
# has_external_api_signal
# ---------------------------------------------------------------------------


class TestHasExternalApiSignal:
    def test_detects_fetch(self) -> None:
        assert has_external_api_signal("I can fetch data from external sources")

    def test_detects_url(self) -> None:
        assert has_external_api_signal("Visit https://example.com for details")

    def test_detects_scrape(self) -> None:
        assert has_external_api_signal("I can scrape websites for information")

    def test_detects_api_call(self) -> None:
        assert has_external_api_signal("I make an api call to the service")

    def test_negative(self) -> None:
        assert not has_external_api_signal("I can help with local data analysis")


# ---------------------------------------------------------------------------
# has_subagent_signal
# ---------------------------------------------------------------------------


class TestHasSubagentSignal:
    def test_detects_subagent(self) -> None:
        assert has_subagent_signal("I can delegate to a subagent for that")

    def test_detects_delegate(self) -> None:
        assert has_subagent_signal("I'll delegate to a specialist")

    def test_detects_worker_agent(self) -> None:
        assert has_subagent_signal("A worker agent handles data processing")

    def test_negative(self) -> None:
        assert not has_subagent_signal("I handle everything myself")


# ---------------------------------------------------------------------------
# extract_json_candidates
# ---------------------------------------------------------------------------


class TestExtractJsonCandidates:
    def test_extracts_raw_json_object(self) -> None:
        text = '{"key": "value", "number": 42}'
        candidates = extract_json_candidates(text)
        assert len(candidates) >= 1
        assert candidates[0] == {"key": "value", "number": 42}

    def test_extracts_fenced_json(self) -> None:
        text = 'Some text\n```json\n{"a": 1}\n```\nMore text'
        candidates = extract_json_candidates(text)
        assert any(c == {"a": 1} for c in candidates)

    def test_extracts_json_array(self) -> None:
        text = '[{"name": "tool1"}, {"name": "tool2"}]'
        candidates = extract_json_candidates(text)
        assert len(candidates) >= 1

    def test_empty_string(self) -> None:
        assert extract_json_candidates("") == []

    def test_no_json(self) -> None:
        assert extract_json_candidates("Just plain text, no JSON here") == []
