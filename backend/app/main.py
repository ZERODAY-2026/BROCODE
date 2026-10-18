"""
DataMind Backend — FastAPI Application

Main API server with endpoints for:
  - Health checks
  - Schema exploration
  - Natural-language question answering
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.gemma_adapter import GemmaAdapter
from app.models import (
    AnswerResponse,
    HealthResponse,
    QuestionRequest,
    SchemaExplorerResponse,
)
from app.query_engine import QueryEngine
from app.snowflake_adapter import SnowflakeAdapter, SnowflakeError

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# Global instances
snowflake_adapter: SnowflakeAdapter | None = None
gemma_adapter: GemmaAdapter | None = None
query_engine: QueryEngine | None = None


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application startup and shutdown lifecycle."""
    global snowflake_adapter, gemma_adapter, query_engine

    settings = get_settings()
    logger.info("DataMind Backend starting...")

    if snowflake_adapter is None:
        snowflake_adapter = SnowflakeAdapter(settings)
    if gemma_adapter is None:
        gemma_adapter = GemmaAdapter(settings)
    if query_engine is None:
        query_engine = QueryEngine(snowflake_adapter, gemma_adapter)

    # Log configuration status (never log secrets)
    logger.info("Snowflake configured: %s", snowflake_adapter.is_configured)
    logger.info("Gemma configured: %s (model: %s)", gemma_adapter.is_configured, settings.gemma_model)

    yield

    logger.info("DataMind Backend shutting down.")


app = FastAPI(
    title="DataMind — Talk to Your Data",
    description="AI-powered data analysis agent using Gemma and Snowflake",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS
settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all exception handler — never expose internals."""
    logger.error("Unhandled exception on %s: %s", request.url.path, type(exc).__name__)
    return JSONResponse(
        status_code=500,
        content={"detail": "An internal error occurred. Please try again."},
    )


# ──────────────────────────────────────────────
# Health
# ──────────────────────────────────────────────

@app.get("/api/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Check health of Snowflake and Gemma connections."""
    sf_ok, sf_msg = False, "Not initialized"
    gm_ok, gm_msg = False, "Not initialized"

    if snowflake_adapter:
        sf_ok, sf_msg = snowflake_adapter.test_connection()

    if gemma_adapter:
        gm_ok, gm_msg = await gemma_adapter.check_availability()

    return HealthResponse(
        status="healthy" if (sf_ok and gm_ok) else "degraded",
        snowflake_connected=sf_ok,
        gemma_available=gm_ok,
        snowflake_message=sf_msg,
        gemma_message=gm_msg,
    )


# ──────────────────────────────────────────────
# Schema Explorer
# ──────────────────────────────────────────────

@app.get("/api/schema", response_model=SchemaExplorerResponse)
async def get_schema() -> SchemaExplorerResponse:
    """Discover and return the available database schema."""
    if not snowflake_adapter:
        return SchemaExplorerResponse(connected=False, error="Backend not initialized.")

    if not snowflake_adapter.is_configured:
        return SchemaExplorerResponse(
            connected=False,
            error="Snowflake is not configured. Set the required environment variables.",
        )

    try:
        schema_info = snowflake_adapter.discover_schema()
        settings = get_settings()
        return SchemaExplorerResponse(
            connected=True,
            schema_info=schema_info,
            database=settings.snowflake_database,
            schema_name=settings.snowflake_schema,
        )
    except SnowflakeError as e:
        return SchemaExplorerResponse(connected=False, error=str(e))


@app.post("/api/schema/refresh", response_model=SchemaExplorerResponse)
async def refresh_schema() -> SchemaExplorerResponse:
    """Force refresh the schema cache."""
    if not snowflake_adapter:
        return SchemaExplorerResponse(connected=False, error="Backend not initialized.")

    try:
        schema_info = snowflake_adapter.discover_schema(force_refresh=True)
        settings = get_settings()
        return SchemaExplorerResponse(
            connected=True,
            schema_info=schema_info,
            database=settings.snowflake_database,
            schema_name=settings.snowflake_schema,
        )
    except SnowflakeError as e:
        return SchemaExplorerResponse(connected=False, error=str(e))


# ──────────────────────────────────────────────
# Question Answering
# ──────────────────────────────────────────────

@app.post("/api/ask", response_model=AnswerResponse)
async def ask_question(request: QuestionRequest) -> AnswerResponse:
    """
    Process a natural-language question through the full pipeline:
    Question → Gemma → SQL Validation → Snowflake → Evidence → Answer
    """
    if not query_engine:
        raise HTTPException(status_code=503, detail="Backend not initialized.")

    response = await query_engine.answer_question(
        question=request.question,
        context=request.context,
    )
    return response


# ──────────────────────────────────────────────
# Example Questions
# ──────────────────────────────────────────────

@app.get("/api/examples")
async def get_example_questions() -> dict:
    """Return example questions based on the configured dataset."""
    return {
        "examples": [
            {
                "question": "Which countries had the highest GDP in the latest available year?",
                "category": "Ranking",
            },
            {
                "question": "What is the average life expectancy by continent?",
                "category": "Aggregation",
            },
            {
                "question": "Compare the population of the top 5 most populated countries over time.",
                "category": "Comparison",
            },
            {
                "question": "Which country has the highest CO2 emissions per capita?",
                "category": "Filtering",
            },
            {
                "question": "Show the trend of global GDP from 2000 to 2020.",
                "category": "Time Series",
            },
            {
                "question": "How many countries have a population over 100 million?",
                "category": "Counting",
            },
        ]
    }
