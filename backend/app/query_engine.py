"""
DataMind Backend — Query Engine

Orchestrates the full question-answering pipeline:
  Question → Gemma interpretation → SQL generation → SQL validation →
  Snowflake execution → Result verification → Evidence-backed answer.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from app.config import get_settings
from app.gemma_adapter import GemmaAdapter, GemmaError
from app.models import AnswerResponse, AnswerStatus, EvidenceDetail
from app.snowflake_adapter import SnowflakeAdapter, SnowflakeError
from app.sql_validator import SQLValidator

logger = logging.getLogger(__name__)


class QueryEngine:
    """
    Main orchestrator for the DataMind question-answering flow.

    Pipeline:
    1. Validate input
    2. Get schema context from Snowflake
    3. Send question + schema to Gemma for interpretation & SQL generation
    4. Validate generated SQL for safety
    5. Execute validated SQL against Snowflake
    6. Verify results
    7. Generate evidence-backed explanation via Gemma
    8. Return structured response
    """

    def __init__(
        self,
        snowflake: SnowflakeAdapter | None = None,
        gemma: GemmaAdapter | None = None,
    ):
        self._settings = get_settings()
        self._snowflake = snowflake or SnowflakeAdapter()
        self._gemma = gemma or GemmaAdapter()

    async def answer_question(
        self,
        question: str,
        context: dict[str, Any] | None = None,
    ) -> AnswerResponse:
        """
        Process a natural-language question through the full pipeline.
        Returns a structured, evidence-backed response.
        """
        # Step 1: Input validation
        if not question or not question.strip():
            return AnswerResponse(
                question=question,
                status=AnswerStatus.ERROR,
                error_message="Please provide a question.",
            )

        question = question.strip()

        # Step 2: Check Snowflake connectivity
        if not self._snowflake.is_configured:
            return AnswerResponse(
                question=question,
                status=AnswerStatus.ERROR,
                error_message=(
                    "Snowflake is not configured. Please set the required environment variables "
                    "(SNOWFLAKE_ACCOUNT, SNOWFLAKE_USER, SNOWFLAKE_PASSWORD, etc.) to connect to your database."
                ),
            )

        # Step 3: Get schema context
        try:
            schema_summary = self._snowflake.get_schema_summary_for_prompt()
        except SnowflakeError as e:
            return AnswerResponse(
                question=question,
                status=AnswerStatus.ERROR,
                error_message=f"Could not discover database schema: {e}",
            )

        if "No tables found" in schema_summary or "unavailable" in schema_summary.lower():
            return AnswerResponse(
                question=question,
                status=AnswerStatus.ERROR,
                error_message=(
                    "No tables found in the configured Snowflake database/schema. "
                    "Please check your SNOWFLAKE_DATABASE and SNOWFLAKE_SCHEMA settings."
                ),
            )

        # Step 4: Send to Gemma for interpretation & SQL generation
        try:
            gemma_response = await self._gemma.interpret_and_generate_sql(
                question=question,
                schema_summary=schema_summary,
                context=context,
            )
        except GemmaError as e:
            return AnswerResponse(
                question=question,
                status=AnswerStatus.ERROR,
                error_message=f"AI model error: {e}",
                evidence=EvidenceDetail(
                    warnings=["Gemma was unavailable. The question could not be processed."],
                ),
            )

        # Step 5: Handle ambiguity
        if gemma_response.is_ambiguous and gemma_response.clarification:
            return AnswerResponse(
                question=question,
                status=AnswerStatus.CLARIFICATION_NEEDED,
                clarification=gemma_response.clarification,
                gemma_interpretation=gemma_response.interpretation,
                evidence=EvidenceDetail(
                    assumptions=gemma_response.assumptions,
                    warnings=["The question was ambiguous. Please provide more details."],
                ),
            )

        # Step 6: Handle unsupported questions
        if gemma_response.is_unsupported:
            return AnswerResponse(
                question=question,
                status=AnswerStatus.UNSUPPORTED,
                answer=gemma_response.unsupported_reason or "This question cannot be answered from the available data.",
                gemma_interpretation=gemma_response.interpretation,
                evidence=EvidenceDetail(
                    limitations=[gemma_response.unsupported_reason] if gemma_response.unsupported_reason else [],
                ),
            )

        # Step 7: Validate SQL
        if not gemma_response.sql:
            return AnswerResponse(
                question=question,
                status=AnswerStatus.ERROR,
                error_message="The AI model did not generate a SQL query. Please try rephrasing your question.",
                gemma_interpretation=gemma_response.interpretation,
            )

        # Build validator with schema-aware allowlists
        validator = SQLValidator(
            allowed_tables=self._snowflake.get_table_names(),
            allowed_columns=self._snowflake.get_column_names(),
            max_rows=self._settings.max_result_rows,
            allowed_databases=self._settings.allowed_database_list,
            allowed_schemas=self._settings.allowed_schema_list,
        )

        validation = validator.validate(gemma_response.sql)

        if not validation.is_valid:
            return AnswerResponse(
                question=question,
                status=AnswerStatus.ERROR,
                error_message=f"Generated SQL failed safety validation: {'; '.join(validation.errors)}",
                gemma_interpretation=gemma_response.interpretation,
                evidence=EvidenceDetail(
                    proposed_sql=gemma_response.sql,
                    warnings=validation.errors,
                    source_tables=gemma_response.relevant_tables,
                    source_columns=gemma_response.relevant_columns,
                ),
            )

        validated_sql = validation.sql

        # Step 8: Execute against Snowflake
        try:
            query_result = self._snowflake.execute_query(
                sql=validated_sql,
                timeout=self._settings.query_timeout_seconds,
                max_rows=self._settings.max_result_rows,
            )
        except SnowflakeError as e:
            return AnswerResponse(
                question=question,
                status=AnswerStatus.ERROR,
                error_message=f"Database query failed: {e}",
                gemma_interpretation=gemma_response.interpretation,
                evidence=EvidenceDetail(
                    executed_sql=validated_sql,
                    source_tables=validation.referenced_tables,
                    source_columns=validation.referenced_columns,
                    execution_status="failed",
                    warnings=validation.warnings,
                ),
            )

        if query_result["status"] == "error":
            return AnswerResponse(
                question=question,
                status=AnswerStatus.ERROR,
                error_message=query_result["error"],
                gemma_interpretation=gemma_response.interpretation,
                evidence=EvidenceDetail(
                    executed_sql=validated_sql,
                    source_tables=validation.referenced_tables,
                    source_columns=validation.referenced_columns,
                    execution_status="error",
                    query_id=query_result.get("query_id"),
                    warnings=validation.warnings,
                ),
            )

        # Step 9: Handle empty results
        data = query_result["data"]
        columns = query_result["columns"]
        row_count = query_result["row_count"]

        if row_count == 0:
            return AnswerResponse(
                question=question,
                status=AnswerStatus.EMPTY_RESULT,
                answer="The query returned no results. This may mean the data doesn't match your criteria, or the relevant records don't exist in the current dataset.",
                data=[],
                columns=columns,
                gemma_interpretation=gemma_response.interpretation,
                evidence=EvidenceDetail(
                    executed_sql=validated_sql,
                    source_tables=validation.referenced_tables,
                    source_columns=validation.referenced_columns,
                    filters_applied=gemma_response.filters,
                    assumptions=gemma_response.assumptions,
                    row_count=0,
                    query_id=query_result.get("query_id"),
                    execution_status="success",
                    execution_time_ms=query_result.get("execution_time_ms"),
                    warnings=validation.warnings + ["Query returned zero rows."],
                ),
            )

        # Step 10: Generate explanation via Gemma
        try:
            explanation = await self._gemma.explain_results(
                question=question,
                sql=validated_sql,
                results=data,
                columns=columns,
                row_count=row_count,
            )
        except GemmaError:
            explanation = self._generate_basic_explanation(question, data, columns, row_count)

        # Step 11: Build evidence
        evidence = EvidenceDetail(
            executed_sql=validated_sql,
            source_tables=validation.referenced_tables or gemma_response.relevant_tables,
            source_columns=validation.referenced_columns or gemma_response.relevant_columns,
            filters_applied=gemma_response.filters,
            assumptions=gemma_response.assumptions,
            row_count=row_count,
            query_id=query_result.get("query_id"),
            execution_status="success",
            execution_time_ms=query_result.get("execution_time_ms"),
            warnings=validation.warnings,
            limitations=self._identify_limitations(data, row_count, query_result),
        )

        # Step 12: Determine final status
        total_rows = query_result.get("total_row_count", row_count)
        status = AnswerStatus.SUCCESS
        if total_rows and total_rows > row_count:
            status = AnswerStatus.PARTIAL
            evidence.warnings.append(
                f"Results truncated: showing {row_count} of {total_rows} total rows."
            )

        return AnswerResponse(
            question=question,
            status=status,
            answer=explanation,
            data=data,
            columns=columns,
            evidence=evidence,
            gemma_interpretation=gemma_response.interpretation,
        )

    def _generate_basic_explanation(
        self,
        question: str,
        data: list[dict],
        columns: list[str],
        row_count: int,
    ) -> str:
        """Fallback explanation when Gemma is unavailable."""
        return (
            f"Query returned {row_count} row{'s' if row_count != 1 else ''} "
            f"with columns: {', '.join(columns)}. "
            f"Please review the data table below for details."
        )

    def _identify_limitations(
        self,
        data: list[dict],
        row_count: int,
        query_result: dict,
    ) -> list[str]:
        """Identify limitations of the result."""
        limitations = []

        # Check for NULL values
        null_columns = set()
        for row in data[:100]:  # Sample first 100 rows
            for k, v in row.items():
                if v is None:
                    null_columns.add(k)
        if null_columns:
            limitations.append(
                f"Some rows contain NULL values in: {', '.join(sorted(null_columns))}"
            )

        # Check truncation
        total = query_result.get("total_row_count", row_count)
        if total and total > row_count:
            limitations.append(
                f"Results limited to {row_count} rows out of {total} total."
            )

        return limitations
