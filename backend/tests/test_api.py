"""
DataMind — API Endpoint Tests

Tests the FastAPI endpoints using TestClient with mocked services.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient

from app.models import AnswerResponse, AnswerStatus, EvidenceDetail, SchemaInfo, TableInfo, ColumnInfo


@pytest.fixture
def client():
    """Create a test client with mocked global adapters."""
    # We need to mock the global adapters before importing the app
    with patch("app.main.snowflake_adapter") as mock_sf, \
         patch("app.main.gemma_adapter") as mock_gm, \
         patch("app.main.query_engine") as mock_qe:

        # Configure mocks
        mock_sf.is_configured = True
        mock_sf.test_connection.return_value = (True, "Connected")

        mock_gm.is_configured = True
        mock_gm.check_availability = AsyncMock(return_value=(True, "Available"))

        mock_qe.answer_question = AsyncMock(return_value=AnswerResponse(
            question="test",
            status=AnswerStatus.SUCCESS,
            answer="Test answer",
            data=[{"col": "val"}],
            columns=["col"],
            evidence=EvidenceDetail(
                executed_sql="SELECT 'val' as col",
                row_count=1,
                execution_status="success",
            ),
        ))

        from app.main import app
        with TestClient(app) as tc:
            yield tc


class TestHealthEndpoint:

    def test_health_check(self, client):
        resp = client.get("/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert "status" in data
        assert "snowflake_connected" in data
        assert "gemma_available" in data


class TestExamplesEndpoint:

    def test_get_examples(self, client):
        resp = client.get("/api/examples")
        assert resp.status_code == 200
        data = resp.json()
        assert "examples" in data
        assert len(data["examples"]) > 0
        for ex in data["examples"]:
            assert "question" in ex
            assert "category" in ex


class TestAskEndpoint:

    def test_ask_valid_question(self, client):
        resp = client.post("/api/ask", json={"question": "What is the GDP?"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert data["answer"] is not None

    def test_ask_empty_question_rejected(self, client):
        resp = client.post("/api/ask", json={"question": ""})
        assert resp.status_code == 422  # Pydantic validation

    def test_ask_missing_question(self, client):
        resp = client.post("/api/ask", json={})
        assert resp.status_code == 422
