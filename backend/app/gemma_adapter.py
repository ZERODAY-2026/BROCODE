"""
DataMind Backend — Gemma Adapter

Handles all interactions with Google Gemma model via Ollama.
Provides structured prompts and parses model responses for:
  1. Question interpretation
  2. SQL generation
  3. Result explanation
  4. Ambiguity detection
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Optional

import httpx

from app.config import Settings, get_settings

logger = logging.getLogger(__name__)


class GemmaError(Exception):
    """Safe error for Gemma operations."""
    pass


class GemmaResponse:
    """Structured response from Gemma."""

    def __init__(
        self,
        interpretation: str = "",
        sql: str = "",
        explanation: str = "",
        is_ambiguous: bool = False,
        clarification: str = "",
        is_unsupported: bool = False,
        unsupported_reason: str = "",
        relevant_tables: list[str] | None = None,
        relevant_columns: list[str] | None = None,
        filters: list[str] | None = None,
        assumptions: list[str] | None = None,
        raw_response: str = "",
    ):
        self.interpretation = interpretation
        self.sql = sql
        self.explanation = explanation
        self.is_ambiguous = is_ambiguous
        self.clarification = clarification
        self.is_unsupported = is_unsupported
        self.unsupported_reason = unsupported_reason
        self.relevant_tables = relevant_tables or []
        self.relevant_columns = relevant_columns or []
        self.filters = filters or []
        self.assumptions = assumptions or []
        self.raw_response = raw_response


class GemmaAdapter:
    """
    Adapter for Google Gemma model via Ollama API.

    Responsibilities:
    - Check model availability
    - Interpret user questions against schema
    - Generate SQL queries
    - Explain query results
    - Detect ambiguity
    """

    def __init__(self, settings: Settings | None = None):
        self._settings = settings or get_settings()
        self._base_url = self._settings.gemma_api_base.rstrip("/")
        self._model = self._settings.gemma_model
        self._timeout = self._settings.gemma_timeout

    @property
    def is_configured(self) -> bool:
        return self._settings.gemma_configured

    async def check_availability(self) -> tuple[bool, str]:
        """Check if Gemma model is available via Ollama."""
        if not self.is_configured:
            return False, "Gemma is not configured."

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                # Check Ollama is running
                resp = await client.get(f"{self._base_url}/api/tags")
                if resp.status_code != 200:
                    return False, f"Ollama API returned status {resp.status_code}."

                tags = resp.json()
                models = [m.get("name", "") for m in tags.get("models", [])]

                # Check if our model is available
                model_base = self._model.split(":")[0]
                available = any(model_base in m for m in models)

                if available:
                    return True, f"Gemma model '{self._model}' is available."
                else:
                    available_str = ", ".join(models[:5]) if models else "none"
                    return False, (
                        f"Model '{self._model}' not found. "
                        f"Available models: {available_str}. "
                        f"Run: ollama pull {self._model}"
                    )
        except httpx.ConnectError:
            return False, (
                "Cannot connect to Ollama. Please ensure Ollama is running. "
                "Start it with: ollama serve"
            )
        except httpx.TimeoutException:
            return False, "Ollama connection timed out."
        except Exception as e:
            logger.error("Gemma availability check failed: %s", type(e).__name__)
            return False, "Failed to check Gemma availability."

    async def _generate(self, prompt: str, system_prompt: str = "") -> str:
        """Send a prompt to Gemma via Ollama and return the response text."""
        if not self.is_configured:
            raise GemmaError("Gemma is not configured.")

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                payload = {
                    "model": self._model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature": 0.1,
                        "top_p": 0.9,
                        "num_predict": 2048,
                    },
                }
                if system_prompt:
                    payload["system"] = system_prompt

                resp = await client.post(
                    f"{self._base_url}/api/generate",
                    json=payload,
                )

                if resp.status_code != 200:
                    raise GemmaError(f"Ollama returned status {resp.status_code}.")

                result = resp.json()
                return result.get("response", "")

        except httpx.ConnectError:
            raise GemmaError(
                "Cannot connect to Ollama. Please ensure Ollama is running (ollama serve)."
            )
        except httpx.TimeoutException:
            raise GemmaError(
                f"Gemma request timed out after {self._timeout}s. "
                "The question may be too complex or the model is overloaded."
            )
        except GemmaError:
            raise
        except Exception as e:
            logger.error("Gemma generation error: %s", type(e).__name__)
            raise GemmaError("An unexpected error occurred communicating with Gemma.") from None

    async def interpret_and_generate_sql(
        self,
        question: str,
        schema_summary: str,
        context: dict[str, Any] | None = None,
    ) -> GemmaResponse:
        """
        Interpret a user question and generate a SQL query.

        This is the primary Gemma integration point. Gemma:
        1. Interprets the natural language question
        2. Maps it to the available schema
        3. Generates a safe SELECT query
        4. Identifies ambiguity or unsupported requests
        """
        system_prompt = """You are DataMind's SQL generation assistant. You help users query their data by converting natural language questions into Snowflake SQL queries.

RULES:
1. Generate ONLY SELECT queries. Never generate INSERT, UPDATE, DELETE, DROP, ALTER, CREATE, or any data-modifying statements.
2. Use only the tables and columns provided in the schema below.
3. Always use fully qualified table names (DATABASE.SCHEMA.TABLE).
4. If the question is ambiguous, set is_ambiguous to true and provide a clarification question.
5. If the question cannot be answered from the available data, set is_unsupported to true and explain why.
6. Be precise with column names — use exact names from the schema.
7. For aggregations, always include appropriate GROUP BY clauses.
8. For time-based analysis, use the date/time columns available in the schema.
9. Add ORDER BY for ranking/comparison queries.
10. Use LIMIT for "top N" type questions.

RESPOND IN EXACTLY THIS JSON FORMAT (no other text):
{
  "interpretation": "Brief explanation of what the user is asking",
  "sql": "SELECT ... FROM ... WHERE ...",
  "relevant_tables": ["TABLE_NAME"],
  "relevant_columns": ["COL1", "COL2"],
  "filters": ["Description of any filters applied"],
  "assumptions": ["Any assumptions made about the question"],
  "is_ambiguous": false,
  "clarification": "",
  "is_unsupported": false,
  "unsupported_reason": ""
}"""

        prompt = f"""AVAILABLE SCHEMA:
{schema_summary}

USER QUESTION: {question}

Generate a Snowflake SQL query to answer this question. Respond with ONLY the JSON object, no other text."""

        raw = await self._generate(prompt, system_prompt)

        return self._parse_sql_response(raw, question)

    async def explain_results(
        self,
        question: str,
        sql: str,
        results: list[dict[str, Any]],
        columns: list[str],
        row_count: int,
    ) -> str:
        """
        Generate a natural-language explanation of query results.

        Gemma explains what was found, grounded in the actual data.
        """
        # Truncate results for prompt efficiency
        preview = results[:20] if len(results) > 20 else results

        system_prompt = """You are DataMind's data explanation assistant. You explain query results in clear, accurate language.

RULES:
1. ONLY describe what the data actually shows. Never invent values or trends not in the data.
2. If the data is empty, say so clearly.
3. Mention specific numbers, values, and column names from the results.
4. Explain what was measured, what filters were applied, and any limitations.
5. Keep explanations concise but informative.
6. If showing percentages or comparisons, derive them from the actual numbers.
7. Note if results were truncated (partial data shown)."""

        prompt = f"""USER QUESTION: {question}

EXECUTED SQL:
{sql}

RESULTS ({row_count} rows returned):
Columns: {', '.join(columns)}
Data preview:
{json.dumps(preview, indent=2, default=str)}

Provide a clear, accurate explanation of these results. Ground every claim in the actual data shown above."""

        try:
            explanation = await self._generate(prompt, system_prompt)
            return explanation.strip()
        except GemmaError:
            return "Unable to generate explanation — Gemma is currently unavailable. Please review the data and SQL directly."

    def _parse_sql_response(self, raw: str, question: str) -> GemmaResponse:
        """Parse Gemma's JSON response for SQL generation."""
        # Try to extract JSON from the response
        json_str = self._extract_json(raw)

        if json_str:
            try:
                data = json.loads(json_str)
                return GemmaResponse(
                    interpretation=data.get("interpretation", ""),
                    sql=data.get("sql", "").strip(),
                    relevant_tables=data.get("relevant_tables", []),
                    relevant_columns=data.get("relevant_columns", []),
                    filters=data.get("filters", []),
                    assumptions=data.get("assumptions", []),
                    is_ambiguous=data.get("is_ambiguous", False),
                    clarification=data.get("clarification", ""),
                    is_unsupported=data.get("is_unsupported", False),
                    unsupported_reason=data.get("unsupported_reason", ""),
                    raw_response=raw,
                )
            except json.JSONDecodeError:
                pass

        # Fallback: Try to extract SQL from raw text
        sql = self._extract_sql_from_text(raw)
        if sql:
            return GemmaResponse(
                interpretation="Extracted SQL from model response.",
                sql=sql,
                raw_response=raw,
            )

        # Could not parse — return as failed
        logger.warning("Could not parse Gemma response for question: %s", question[:100])
        return GemmaResponse(
            interpretation="Could not parse model response.",
            is_unsupported=True,
            unsupported_reason="The AI model did not return a valid response. Please try rephrasing your question.",
            raw_response=raw,
        )

    def _extract_json(self, text: str) -> str | None:
        """Extract JSON object from text that may contain other content."""
        # Try direct parse first
        text = text.strip()
        if text.startswith("{"):
            # Find the matching closing brace
            depth = 0
            for i, ch in enumerate(text):
                if ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        return text[: i + 1]

        # Look for JSON in code blocks
        patterns = [
            r'```json\s*\n(.*?)\n\s*```',
            r'```\s*\n(.*?)\n\s*```',
            r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}',
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.DOTALL)
            if match:
                candidate = match.group(1) if match.lastindex else match.group(0)
                candidate = candidate.strip()
                if candidate.startswith("{"):
                    return candidate

        return None

    def _extract_sql_from_text(self, text: str) -> str | None:
        """Try to extract a SQL SELECT statement from raw text."""
        # Look for SQL in code blocks
        sql_patterns = [
            r'```sql\s*\n(.*?)\n\s*```',
            r'```\s*\n(SELECT.*?)\n\s*```',
        ]
        for pattern in sql_patterns:
            match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
            if match:
                return match.group(1).strip()

        # Look for bare SELECT statement
        match = re.search(r'(SELECT\s+.+?)(?:\n\n|\Z)', text, re.DOTALL | re.IGNORECASE)
        if match:
            return match.group(1).strip()

        return None
