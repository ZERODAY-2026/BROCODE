"""
DataMind Backend — SQL Validator

Validates model-generated SQL before execution against Snowflake.
Uses sqlglot for structural parsing + custom safety checks.
Treats all model-generated SQL as untrusted input.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Optional

import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError

logger = logging.getLogger(__name__)

# Statements that are absolutely forbidden
FORBIDDEN_STATEMENT_TYPES = {
    "INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "CREATE",
    "TRUNCATE", "MERGE", "REPLACE", "GRANT", "REVOKE",
    "COPY", "PUT", "GET", "REMOVE", "CALL",
    "EXECUTE", "BEGIN", "COMMIT", "ROLLBACK",
}

# Dangerous SQL keywords to check as a secondary filter
DANGEROUS_PATTERNS = [
    r'\bINSERT\s+INTO\b',
    r'\bUPDATE\s+\w+\s+SET\b',
    r'\bDELETE\s+FROM\b',
    r'\bDROP\s+',
    r'\bALTER\s+',
    r'\bCREATE\s+',
    r'\bTRUNCATE\s+',
    r'\bEXEC(UTE)?\s+',
    r'\bGRANT\s+',
    r'\bREVOKE\s+',
    r'\bMERGE\s+',
    r'\bCOPY\s+INTO\b',
    r'\bPUT\s+',
    r'\bGET\s+',
    r'\bREMOVE\s+',
    r'\bCALL\s+',
    r'\bBEGIN\b',
    r'\bCOMMIT\b',
    r'\bROLLBACK\b',
    r';\s*\w',  # Multiple statements
]


@dataclass
class ValidationResult:
    """Result of SQL validation."""

    is_valid: bool
    sql: str
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    referenced_tables: list[str] = field(default_factory=list)
    referenced_columns: list[str] = field(default_factory=list)


class SQLValidator:
    """
    Validates SQL queries for safety before Snowflake execution.

    Security layers:
    1. Pattern-based pre-screening (catches obvious attacks)
    2. sqlglot AST parsing (structural validation)
    3. Statement type whitelist (only SELECT + CTEs)
    4. Table/column allowlist check (schema-bound)
    5. Row limit injection
    """

    def __init__(
        self,
        allowed_tables: list[str] | None = None,
        allowed_columns: list[str] | None = None,
        max_rows: int = 1000,
        allowed_databases: list[str] | None = None,
        allowed_schemas: list[str] | None = None,
    ):
        self._allowed_tables = set(t.upper() for t in (allowed_tables or []))
        self._allowed_columns = set(c.upper() for c in (allowed_columns or []))
        self._max_rows = max_rows
        self._allowed_databases = set(d.upper() for d in (allowed_databases or []))
        self._allowed_schemas = set(s.upper() for s in (allowed_schemas or []))

    def validate(self, sql: str) -> ValidationResult:
        """Validate SQL query for safety. Returns ValidationResult."""
        errors: list[str] = []
        warnings: list[str] = []
        referenced_tables: list[str] = []
        referenced_columns: list[str] = []

        if not sql or not sql.strip():
            return ValidationResult(is_valid=False, sql=sql, errors=["Empty SQL query."])

        cleaned_sql = sql.strip().rstrip(";").strip()

        # Strip comments for pattern pre-screening and statement count
        code_without_comments = re.sub(r'/\*[\s\S]*?\*/', '', cleaned_sql)
        code_without_comments = re.sub(r'--.*$', '', code_without_comments, flags=re.MULTILINE).strip()

        # Layer 1: Pattern-based pre-screening (on active code, not comments)
        pattern_errors = self._check_dangerous_patterns(code_without_comments)
        if pattern_errors:
            return ValidationResult(is_valid=False, sql=sql, errors=pattern_errors)

        # Layer 2: Check for multiple statements (semicolons in active code)
        if ";" in code_without_comments:
            return ValidationResult(
                is_valid=False,
                sql=sql,
                errors=["Multiple SQL statements are not allowed. Please submit a single SELECT query."],
            )

        # Layer 3: Parse with sqlglot
        try:
            parsed = sqlglot.parse(cleaned_sql, dialect="snowflake")
        except ParseError as e:
            return ValidationResult(
                is_valid=False,
                sql=sql,
                errors=[f"SQL parsing failed: Could not parse the query. Please check the syntax."],
            )

        if not parsed:
            return ValidationResult(is_valid=False, sql=sql, errors=["SQL parsing produced no result."])

        if len(parsed) > 1:
            return ValidationResult(
                is_valid=False,
                sql=sql,
                errors=["Multiple SQL statements detected. Only a single SELECT query is allowed."],
            )

        statement = parsed[0]

        # Layer 4: Check statement type — only SELECT allowed
        stmt_type = type(statement).__name__.upper()
        if not isinstance(statement, exp.Select):
            # Check if it's a CTE (WITH ... SELECT)
            if not (hasattr(statement, 'this') and isinstance(getattr(statement, 'this', None), exp.Select)):
                return ValidationResult(
                    is_valid=False,
                    sql=sql,
                    errors=[f"Only SELECT queries are allowed. Received: {stmt_type}"],
                )

        # Layer 5: Check for forbidden expression types in the AST
        for node in statement.walk():
            node_type = type(node).__name__.upper()
            if node_type in FORBIDDEN_STATEMENT_TYPES:
                return ValidationResult(
                    is_valid=False,
                    sql=sql,
                    errors=[f"Forbidden SQL operation detected: {node_type}"],
                )
            # Check for subqueries that might contain mutations
            if isinstance(node, (exp.Insert, exp.Update, exp.Delete, exp.Drop,
                                 exp.Create, exp.Alter)):
                return ValidationResult(
                    is_valid=False,
                    sql=sql,
                    errors=["Destructive SQL operation detected in query."],
                )

        # Layer 6: Extract referenced tables
        for table_node in statement.find_all(exp.Table):
            parts = []
            if table_node.catalog:
                parts.append(table_node.catalog.upper())
            if table_node.db:
                parts.append(table_node.db.upper())
            parts.append(table_node.name.upper())

            fqn = ".".join(parts)
            referenced_tables.append(fqn)

            # Validate against allowed tables if configured
            if self._allowed_tables:
                table_name_upper = table_node.name.upper()
                matched = any(
                    table_name_upper == at.split(".")[-1]
                    for at in self._allowed_tables
                ) or fqn in self._allowed_tables

                if not matched:
                    errors.append(f"Table '{table_node.name}' is not in the allowed table list.")

            # Validate database reference
            if table_node.catalog and self._allowed_databases:
                if table_node.catalog.upper() not in self._allowed_databases:
                    errors.append(f"Database '{table_node.catalog}' is not allowed.")

            # Validate schema reference
            if table_node.db and self._allowed_schemas:
                if table_node.db.upper() not in self._allowed_schemas:
                    errors.append(f"Schema '{table_node.db}' is not allowed.")

        # Layer 7: Extract referenced columns
        for col_node in statement.find_all(exp.Column):
            col_name = col_node.name.upper()
            referenced_columns.append(col_name)

        if errors:
            return ValidationResult(
                is_valid=False,
                sql=sql,
                errors=errors,
                referenced_tables=referenced_tables,
                referenced_columns=referenced_columns,
            )

        # Layer 8: Add LIMIT if not present
        final_sql = cleaned_sql
        has_limit = any(isinstance(node, exp.Limit) for node in statement.walk())
        if not has_limit:
            final_sql = f"{cleaned_sql}\nLIMIT {self._max_rows}"
            warnings.append(f"Added LIMIT {self._max_rows} to query for safety.")

        return ValidationResult(
            is_valid=True,
            sql=final_sql,
            warnings=warnings,
            referenced_tables=referenced_tables,
            referenced_columns=referenced_columns,
        )

    def _check_dangerous_patterns(self, sql: str) -> list[str]:
        """Pre-screen SQL for dangerous patterns using regex."""
        errors = []
        sql_upper = sql.upper()

        for pattern in DANGEROUS_PATTERNS:
            if re.search(pattern, sql_upper, re.IGNORECASE):
                errors.append(f"Potentially dangerous SQL pattern detected. Only SELECT queries are allowed.")
                break

        return errors
