"""
DataMind — Query Engine Unit Tests (Mocked)

Tests the full pipeline with mocked Snowflake and Gemma adapters.
Clearly labeled as MOCKED tests — not live integration tests.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock
import json

from app.query_engine import QueryEngine
from app.models import AnswerStatus
from app.gemma_adapter import GemmaResponse, GemmaError
from app.snowflake_adapter import SnowflakeError


@pytest.fixture
def mock_snowflake():
    """Create a mock Snowflake adapter."""
    sf = MagicMock()
    sf.is_configured = True
    sf.get_schema_summary_for_prompt.return_value = (
        "Available tables and columns:\n\n"
        "Table: DATAMIND_DB.PUBLIC.WORLD_INDICATORS (~1000 rows)\n"
        "  - COUNTRY (TEXT, nullable)\n"
        "  - YEAR (NUMBER, not null)\n"
        "  - GDP (NUMBER, nullable)\n"
        "  - POPULATION (NUMBER, nullable)\n"
    )
    sf.get_table_names.return_value = ["DATAMIND_DB.PUBLIC.WORLD_INDICATORS"]
    sf.get_column_names.return_value = ["COUNTRY", "YEAR", "GDP", "POPULATION"]
    return sf


@pytest.fixture
def mock_gemma():
    """Create a mock Gemma adapter."""
    gm = MagicMock()
    gm.is_configured = True
    return gm


@pytest.fixture
def engine(mock_snowflake, mock_gemma):
    return QueryEngine(snowflake=mock_snowflake, gemma=mock_gemma)


class TestSuccessfulQuery:
    """Test successful question-answering flow (MOCKED)."""

    @pytest.mark.asyncio
    async def test_full_pipeline_success(self, engine, mock_snowflake, mock_gemma):
        """MOCKED: Test complete pipeline with valid question."""
        # Gemma returns a valid SQL response
        mock_gemma.interpret_and_generate_sql = AsyncMock(return_value=GemmaResponse(
            interpretation="User wants top countries by GDP",
            sql="SELECT COUNTRY, GDP FROM DATAMIND_DB.PUBLIC.WORLD_INDICATORS ORDER BY GDP DESC LIMIT 5",
            relevant_tables=["WORLD_INDICATORS"],
            relevant_columns=["COUNTRY", "GDP"],
            filters=["Ordered by GDP descending"],
            assumptions=["Using all available years"],
        ))

        # Snowflake returns data
        mock_snowflake.execute_query.return_value = {
            "data": [
                {"COUNTRY": "USA", "GDP": 21427700},
                {"COUNTRY": "China", "GDP": 14342900},
            ],
            "columns": ["COUNTRY", "GDP"],
            "row_count": 2,
            "total_row_count": 2,
            "query_id": "01abc-test",
            "execution_time_ms": 150.5,
            "status": "success",
            "error": None,
        }

        # Gemma explains results
        mock_gemma.explain_results = AsyncMock(return_value="The USA has the highest GDP at $21.4M, followed by China at $14.3M.")

        result = await engine.answer_question("Which countries have the highest GDP?")

        assert result.status == AnswerStatus.SUCCESS
        assert result.answer is not None
        assert result.data is not None
        assert len(result.data) == 2
        assert result.evidence is not None
        assert result.evidence.executed_sql is not None
        assert result.evidence.query_id == "01abc-test"
        assert result.evidence.execution_status == "success"


class TestEmptyResults:
    """Test empty result handling (MOCKED)."""

    @pytest.mark.asyncio
    async def test_empty_result(self, engine, mock_snowflake, mock_gemma):
        mock_gemma.interpret_and_generate_sql = AsyncMock(return_value=GemmaResponse(
            interpretation="Looking for data",
            sql="SELECT * FROM DATAMIND_DB.PUBLIC.WORLD_INDICATORS WHERE COUNTRY = 'Atlantis'",
        ))
        mock_snowflake.execute_query.return_value = {
            "data": [],
            "columns": ["COUNTRY", "GDP"],
            "row_count": 0,
            "total_row_count": 0,
            "query_id": "01abc-empty",
            "execution_time_ms": 50,
            "status": "success",
            "error": None,
        }

        result = await engine.answer_question("Show data for Atlantis")
        assert result.status == AnswerStatus.EMPTY_RESULT


class TestAmbiguity:
    """Test ambiguity handling (MOCKED)."""

    @pytest.mark.asyncio
    async def test_ambiguous_question(self, engine, mock_gemma):
        mock_gemma.interpret_and_generate_sql = AsyncMock(return_value=GemmaResponse(
            interpretation="Multiple interpretations",
            is_ambiguous=True,
            clarification="Which year are you asking about: 2019, 2020, or the latest available?",
        ))

        result = await engine.answer_question("Show me the GDP")
        assert result.status == AnswerStatus.CLARIFICATION_NEEDED
        assert result.clarification is not None


class TestUnsupported:
    """Test unsupported question handling (MOCKED)."""

    @pytest.mark.asyncio
    async def test_unsupported_question(self, engine, mock_gemma):
        mock_gemma.interpret_and_generate_sql = AsyncMock(return_value=GemmaResponse(
            interpretation="Weather question",
            is_unsupported=True,
            unsupported_reason="No weather data in the dataset.",
        ))

        result = await engine.answer_question("What's the weather in Tokyo?")
        assert result.status == AnswerStatus.UNSUPPORTED


class TestErrorHandling:
    """Test error conditions (MOCKED)."""

    @pytest.mark.asyncio
    async def test_snowflake_not_configured(self, mock_gemma):
        sf = MagicMock()
        sf.is_configured = False
        engine = QueryEngine(snowflake=sf, gemma=mock_gemma)

        result = await engine.answer_question("test question")
        assert result.status == AnswerStatus.ERROR
        assert "not configured" in result.error_message.lower()

    @pytest.mark.asyncio
    async def test_gemma_error(self, engine, mock_gemma):
        mock_gemma.interpret_and_generate_sql = AsyncMock(
            side_effect=GemmaError("Cannot connect to Ollama")
        )
        result = await engine.answer_question("test question")
        assert result.status == AnswerStatus.ERROR

    @pytest.mark.asyncio
    async def test_snowflake_query_error(self, engine, mock_snowflake, mock_gemma):
        mock_gemma.interpret_and_generate_sql = AsyncMock(return_value=GemmaResponse(
            interpretation="Test",
            sql="SELECT COUNTRY FROM DATAMIND_DB.PUBLIC.WORLD_INDICATORS",
        ))
        mock_snowflake.execute_query.return_value = {
            "data": [],
            "columns": [],
            "row_count": 0,
            "total_row_count": 0,
            "query_id": None,
            "execution_time_ms": 0,
            "status": "error",
            "error": "Table not found",
        }

        result = await engine.answer_question("test")
        assert result.status == AnswerStatus.ERROR

    @pytest.mark.asyncio
    async def test_empty_question(self, engine):
        result = await engine.answer_question("")
        assert result.status == AnswerStatus.ERROR

    @pytest.mark.asyncio
    async def test_no_sql_generated(self, engine, mock_gemma):
        mock_gemma.interpret_and_generate_sql = AsyncMock(return_value=GemmaResponse(
            interpretation="Could not understand",
            sql="",
        ))
        result = await engine.answer_question("asdfghjkl")
        assert result.status == AnswerStatus.ERROR


class TestSQLValidationInPipeline:
    """Test that SQL validation catches bad queries in the pipeline (MOCKED)."""

    @pytest.mark.asyncio
    async def test_destructive_sql_rejected(self, engine, mock_gemma):
        mock_gemma.interpret_and_generate_sql = AsyncMock(return_value=GemmaResponse(
            interpretation="Test",
            sql="DROP TABLE DATAMIND_DB.PUBLIC.WORLD_INDICATORS",
        ))
        result = await engine.answer_question("delete all data")
        assert result.status == AnswerStatus.ERROR
        assert "safety validation" in result.error_message.lower() or "select" in result.error_message.lower()

    @pytest.mark.asyncio
    async def test_multiple_statements_rejected(self, engine, mock_gemma):
        mock_gemma.interpret_and_generate_sql = AsyncMock(return_value=GemmaResponse(
            interpretation="Test",
            sql="SELECT 1; DROP TABLE x",
        ))
        result = await engine.answer_question("test")
        assert result.status == AnswerStatus.ERROR
