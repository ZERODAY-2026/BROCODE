"""
DataMind Backend — Pydantic Models

Shared request/response schemas for the API.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class AnswerStatus(str, Enum):
    SUCCESS = "success"
    CLARIFICATION_NEEDED = "clarification_needed"
    EMPTY_RESULT = "empty_result"
    ERROR = "error"
    UNSUPPORTED = "unsupported"
    PARTIAL = "partial"


class QuestionRequest(BaseModel):
    """User's natural-language question."""

    question: str = Field(..., min_length=1, max_length=2000, description="Natural-language question")
    context: Optional[dict[str, Any]] = Field(default=None, description="Optional context like selected table")


class ColumnInfo(BaseModel):
    """Schema information for a single column."""

    name: str
    data_type: str
    nullable: bool = True
    comment: Optional[str] = None


class TableInfo(BaseModel):
    """Schema information for a single table."""

    database: str
    schema_name: str  # 'schema' is reserved
    name: str
    columns: list[ColumnInfo] = []
    row_count: Optional[int] = None
    comment: Optional[str] = None


class SchemaInfo(BaseModel):
    """Full discovered schema."""

    tables: list[TableInfo] = []
    discovered_at: Optional[str] = None


class EvidenceDetail(BaseModel):
    """Inspectable evidence for a query answer."""

    executed_sql: Optional[str] = None
    proposed_sql: Optional[str] = None
    source_tables: list[str] = []
    source_columns: list[str] = []
    filters_applied: list[str] = []
    assumptions: list[str] = []
    row_count: Optional[int] = None
    query_id: Optional[str] = None
    execution_status: Optional[str] = None
    execution_time_ms: Optional[float] = None
    warnings: list[str] = []
    limitations: list[str] = []


class AnswerResponse(BaseModel):
    """Complete response to a user question."""

    question: str
    status: AnswerStatus
    answer: Optional[str] = None
    data: Optional[list[dict[str, Any]]] = None
    columns: Optional[list[str]] = None
    evidence: Optional[EvidenceDetail] = None
    clarification: Optional[str] = None
    error_message: Optional[str] = None
    gemma_interpretation: Optional[str] = None
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())


class HealthResponse(BaseModel):
    """Health check response."""

    status: str
    snowflake_connected: bool
    gemma_available: bool
    snowflake_message: str = ""
    gemma_message: str = ""
    version: str = "1.0.0"


class SchemaExplorerResponse(BaseModel):
    """Response for schema explorer."""

    connected: bool
    schema_info: Optional[SchemaInfo] = None
    error: Optional[str] = None
    database: str = ""
    schema_name: str = ""
