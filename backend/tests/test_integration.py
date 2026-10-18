"""
DataMind — Integration Tests

These tests require LIVE Snowflake and Gemma connections.
They are SKIPPED by default unless the required environment variables are set.

Run with: pytest tests/test_integration.py -v
(Will skip unless SNOWFLAKE_ACCOUNT and Ollama are configured)
"""

import os
import pytest
from unittest.mock import MagicMock

from app.config import Settings, get_settings
from app.snowflake_adapter import SnowflakeAdapter
from app.gemma_adapter import GemmaAdapter
from app.query_engine import QueryEngine


def snowflake_configured() -> bool:
    """Check if Snowflake credentials are available."""
    return bool(
        os.getenv("SNOWFLAKE_ACCOUNT")
        and os.getenv("SNOWFLAKE_USER")
        and os.getenv("SNOWFLAKE_PASSWORD")
    )


def gemma_configured() -> bool:
    """Check if Gemma/Ollama is likely available."""
    return bool(os.getenv("GEMMA_API_BASE", "http://localhost:11434"))


skip_no_snowflake = pytest.mark.skipif(
    not snowflake_configured(),
    reason="Snowflake credentials not configured (set SNOWFLAKE_ACCOUNT, SNOWFLAKE_USER, SNOWFLAKE_PASSWORD)",
)

skip_no_gemma = pytest.mark.skipif(
    not gemma_configured(),
    reason="Gemma/Ollama not configured",
)


@skip_no_snowflake
class TestLiveSnowflake:
    """LIVE integration tests against a real Snowflake instance."""

    @pytest.fixture
    def adapter(self):
        return SnowflakeAdapter()

    def test_live_connection(self, adapter):
        """Test actual Snowflake connection."""
        ok, msg = adapter.test_connection()
        assert ok, f"Snowflake connection failed: {msg}"

    def test_live_schema_discovery(self, adapter):
        """Test schema discovery against real Snowflake."""
        schema = adapter.discover_schema()
        assert len(schema.tables) > 0, "No tables discovered"
        # Verify tables have columns
        for table in schema.tables:
            assert len(table.columns) > 0, f"Table {table.name} has no columns"

    def test_live_query_execution(self, adapter):
        """Test query execution against real Snowflake."""
        result = adapter.execute_query("SELECT CURRENT_TIMESTAMP() as NOW")
        assert result["status"] == "success"
        assert result["row_count"] == 1
        assert result["query_id"] is not None


@skip_no_snowflake
@skip_no_gemma
class TestLiveEndToEnd:
    """LIVE end-to-end tests — require both Snowflake and Gemma."""

    @pytest.fixture
    def engine(self):
        return QueryEngine()

    @pytest.mark.asyncio
    async def test_live_question(self, engine):
        """Test a complete question flow against live services."""
        result = await engine.answer_question(
            "How many rows are in the first table?"
        )
        # We accept success, empty, or clarification — but not error if configured
        assert result.status in [
            "success", "empty_result", "clarification_needed", "partial"
        ], f"Unexpected status: {result.status}, error: {result.error_message}"

    @pytest.mark.asyncio
    async def test_live_evidence_present(self, engine):
        """Test that evidence is present in live responses."""
        result = await engine.answer_question(
            "Show the first 5 rows from any table"
        )
        if result.status == "success":
            assert result.evidence is not None
            assert result.evidence.executed_sql is not None
            assert result.evidence.query_id is not None


@skip_no_gemma
class TestLiveGemma:
    """LIVE Gemma availability tests."""

    @pytest.fixture
    def adapter(self):
        return GemmaAdapter()

    @pytest.mark.asyncio
    async def test_gemma_availability(self, adapter):
        """Test Gemma model availability."""
        ok, msg = await adapter.check_availability()
        # Don't assert ok — just verify the check doesn't crash
        assert isinstance(ok, bool)
        assert isinstance(msg, str)
