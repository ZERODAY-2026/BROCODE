"""
DataMind — Gemma Adapter Unit Tests

Tests Gemma response parsing, error handling, and structured output.
These are unit tests that do NOT require a live Ollama instance.
"""

import pytest
from app.gemma_adapter import GemmaAdapter, GemmaResponse


class TestGemmaResponseParsing:
    """Test JSON response parsing from Gemma."""

    @pytest.fixture
    def adapter(self):
        return GemmaAdapter()

    def test_parse_valid_json_response(self, adapter):
        raw = '''{
            "interpretation": "User wants top GDP countries",
            "sql": "SELECT COUNTRY, GDP FROM DB.PUBLIC.WORLD ORDER BY GDP DESC LIMIT 10",
            "relevant_tables": ["WORLD"],
            "relevant_columns": ["COUNTRY", "GDP"],
            "filters": ["Ordered by GDP descending"],
            "assumptions": ["Using latest year"],
            "is_ambiguous": false,
            "clarification": "",
            "is_unsupported": false,
            "unsupported_reason": ""
        }'''
        result = adapter._parse_sql_response(raw, "test question")
        assert result.sql == "SELECT COUNTRY, GDP FROM DB.PUBLIC.WORLD ORDER BY GDP DESC LIMIT 10"
        assert result.interpretation == "User wants top GDP countries"
        assert not result.is_ambiguous
        assert not result.is_unsupported

    def test_parse_json_in_code_block(self, adapter):
        raw = '''Here is the query:
```json
{
    "interpretation": "Test",
    "sql": "SELECT 1",
    "relevant_tables": [],
    "relevant_columns": [],
    "filters": [],
    "assumptions": [],
    "is_ambiguous": false,
    "clarification": "",
    "is_unsupported": false,
    "unsupported_reason": ""
}
```'''
        result = adapter._parse_sql_response(raw, "test")
        assert result.sql == "SELECT 1"

    def test_parse_ambiguous_response(self, adapter):
        raw = '''{
            "interpretation": "Unclear time period",
            "sql": "",
            "relevant_tables": ["WORLD"],
            "relevant_columns": [],
            "filters": [],
            "assumptions": [],
            "is_ambiguous": true,
            "clarification": "Which year are you interested in?",
            "is_unsupported": false,
            "unsupported_reason": ""
        }'''
        result = adapter._parse_sql_response(raw, "test")
        assert result.is_ambiguous
        assert "year" in result.clarification.lower()

    def test_parse_unsupported_response(self, adapter):
        raw = '''{
            "interpretation": "Question about weather",
            "sql": "",
            "relevant_tables": [],
            "relevant_columns": [],
            "filters": [],
            "assumptions": [],
            "is_ambiguous": false,
            "clarification": "",
            "is_unsupported": true,
            "unsupported_reason": "No weather data available"
        }'''
        result = adapter._parse_sql_response(raw, "test")
        assert result.is_unsupported
        assert "weather" in result.unsupported_reason.lower()

    def test_parse_sql_from_code_block_fallback(self, adapter):
        raw = '''I'll generate a query for you:
```sql
SELECT COUNTRY, GDP FROM DB.PUBLIC.WORLD ORDER BY GDP DESC LIMIT 5
```
This will show the top 5 countries.'''
        result = adapter._parse_sql_response(raw, "test")
        assert "SELECT" in result.sql
        assert "GDP" in result.sql

    def test_parse_bare_select_fallback(self, adapter):
        raw = "SELECT COUNTRY FROM DB.PUBLIC.WORLD WHERE YEAR = 2020"
        result = adapter._parse_sql_response(raw, "test")
        assert "SELECT" in result.sql

    def test_parse_garbage_response(self, adapter):
        raw = "I don't understand the question at all. Blah blah."
        result = adapter._parse_sql_response(raw, "test")
        assert result.is_unsupported

    def test_parse_empty_response(self, adapter):
        raw = ""
        result = adapter._parse_sql_response(raw, "test")
        assert result.is_unsupported


class TestGemmaJsonExtraction:
    """Test the JSON extraction helper."""

    @pytest.fixture
    def adapter(self):
        return GemmaAdapter()

    def test_extract_plain_json(self, adapter):
        text = '{"key": "value"}'
        result = adapter._extract_json(text)
        assert result is not None

    def test_extract_json_with_surrounding_text(self, adapter):
        text = 'Here is the result:\n{"sql": "SELECT 1"}\nDone.'
        result = adapter._extract_json(text)
        assert result is not None

    def test_extract_json_from_code_block(self, adapter):
        text = '```json\n{"sql": "SELECT 1"}\n```'
        result = adapter._extract_json(text)
        assert result is not None

    def test_no_json_found(self, adapter):
        text = "Just some plain text with no JSON."
        result = adapter._extract_json(text)
        assert result is None


class TestGemmaSQLExtraction:
    """Test SQL extraction fallback."""

    @pytest.fixture
    def adapter(self):
        return GemmaAdapter()

    def test_extract_sql_from_code_block(self, adapter):
        text = '```sql\nSELECT * FROM table1\n```'
        result = adapter._extract_sql_from_text(text)
        assert result == "SELECT * FROM table1"

    def test_extract_bare_select(self, adapter):
        text = "Here is the query:\nSELECT * FROM table1 WHERE id = 1"
        result = adapter._extract_sql_from_text(text)
        assert result is not None
        assert "SELECT" in result

    def test_no_sql_found(self, adapter):
        text = "No SQL here, just text."
        result = adapter._extract_sql_from_text(text)
        assert result is None
