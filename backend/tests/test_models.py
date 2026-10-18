"""
DataMind — Model & API Unit Tests

Tests Pydantic models, input validation, and API endpoints (mocked).
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient

from app.models import (
    AnswerResponse,
    AnswerStatus,
    EvidenceDetail,
    QuestionRequest,
    HealthResponse,
    ColumnInfo,
    TableInfo,
    SchemaInfo,
)


class TestQuestionRequest:
    """Test question input validation."""

    def test_valid_question(self):
        req = QuestionRequest(question="What is the average GDP?")
        assert req.question == "What is the average GDP?"

    def test_empty_question_rejected(self):
        with pytest.raises(Exception):
            QuestionRequest(question="")

    def test_too_long_question_rejected(self):
        with pytest.raises(Exception):
            QuestionRequest(question="a" * 2001)

    def test_question_with_context(self):
        req = QuestionRequest(question="Show GDP", context={"table": "WORLD_DATA"})
        assert req.context == {"table": "WORLD_DATA"}


class TestAnswerResponse:
    """Test answer response structure."""

    def test_success_response(self):
        resp = AnswerResponse(
            question="test",
            status=AnswerStatus.SUCCESS,
            answer="The answer is 42.",
            data=[{"val": 42}],
            columns=["val"],
            evidence=EvidenceDetail(
                executed_sql="SELECT 42 as val",
                row_count=1,
                execution_status="success",
            ),
        )
        assert resp.status == AnswerStatus.SUCCESS
        assert resp.evidence.executed_sql == "SELECT 42 as val"
        assert resp.timestamp  # auto-generated

    def test_error_response(self):
        resp = AnswerResponse(
            question="test",
            status=AnswerStatus.ERROR,
            error_message="Connection failed",
        )
        assert resp.status == AnswerStatus.ERROR

    def test_clarification_response(self):
        resp = AnswerResponse(
            question="test",
            status=AnswerStatus.CLARIFICATION_NEEDED,
            clarification="Which year do you mean?",
        )
        assert resp.clarification == "Which year do you mean?"

    def test_empty_result_response(self):
        resp = AnswerResponse(
            question="test",
            status=AnswerStatus.EMPTY_RESULT,
            answer="No data found.",
            data=[],
            columns=["a", "b"],
        )
        assert resp.data == []


class TestEvidenceDetail:
    """Test evidence structure."""

    def test_full_evidence(self):
        ev = EvidenceDetail(
            executed_sql="SELECT * FROM t",
            proposed_sql="SELECT * FROM t",
            source_tables=["DB.SCHEMA.TABLE"],
            source_columns=["COL1", "COL2"],
            filters_applied=["YEAR = 2020"],
            assumptions=["Using latest year"],
            row_count=10,
            query_id="01abc-def",
            execution_status="success",
            execution_time_ms=123.45,
            warnings=["Truncated"],
            limitations=["NULL values present"],
        )
        assert ev.query_id == "01abc-def"
        assert len(ev.source_tables) == 1

    def test_minimal_evidence(self):
        ev = EvidenceDetail()
        assert ev.executed_sql is None
        assert ev.row_count is None


class TestSchemaModels:
    """Test schema-related models."""

    def test_column_info(self):
        col = ColumnInfo(name="GDP", data_type="NUMBER", nullable=True)
        assert col.name == "GDP"

    def test_table_info(self):
        table = TableInfo(
            database="DB",
            schema_name="PUBLIC",
            name="INDICATORS",
            columns=[ColumnInfo(name="GDP", data_type="NUMBER")],
            row_count=1000,
        )
        assert table.row_count == 1000
        assert len(table.columns) == 1

    def test_schema_info(self):
        schema = SchemaInfo(
            tables=[
                TableInfo(database="DB", schema_name="S", name="T1"),
                TableInfo(database="DB", schema_name="S", name="T2"),
            ]
        )
        assert len(schema.tables) == 2


class TestHealthResponse:
    """Test health response model."""

    def test_healthy(self):
        h = HealthResponse(
            status="healthy",
            snowflake_connected=True,
            gemma_available=True,
            snowflake_message="Connected",
            gemma_message="Available",
        )
        assert h.status == "healthy"

    def test_degraded(self):
        h = HealthResponse(
            status="degraded",
            snowflake_connected=False,
            gemma_available=True,
            snowflake_message="Not configured",
            gemma_message="Available",
        )
        assert h.snowflake_connected is False
