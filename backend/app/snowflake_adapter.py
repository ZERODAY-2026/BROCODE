"""
DataMind Backend — Snowflake Adapter

Handles all Snowflake interactions: connection, schema discovery, query execution.
Uses the official snowflake-connector-python.
"""

from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from typing import Any, Generator, Optional

import snowflake.connector
from snowflake.connector import DictCursor
from snowflake.connector.errors import (
    DatabaseError,
    InterfaceError,
    OperationalError,
    ProgrammingError,
)

from app.config import Settings, get_settings
from app.models import ColumnInfo, SchemaInfo, TableInfo

logger = logging.getLogger(__name__)


class SnowflakeError(Exception):
    """Safe error for Snowflake operations — never exposes credentials."""

    pass


class SnowflakeAdapter:
    """Manages Snowflake connections, schema discovery, and query execution."""

    def __init__(self, settings: Settings | None = None):
        self._settings = settings or get_settings()
        self._cached_schema: SchemaInfo | None = None

    @property
    def is_configured(self) -> bool:
        return self._settings.snowflake_configured

    @contextmanager
    def _get_connection(self) -> Generator[snowflake.connector.SnowflakeConnection, None, None]:
        """Create a managed Snowflake connection."""
        if not self.is_configured:
            raise SnowflakeError(
                "Snowflake is not configured. Please set SNOWFLAKE_ACCOUNT, "
                "SNOWFLAKE_USER, and SNOWFLAKE_PASSWORD environment variables."
            )

        conn = None
        try:
            connect_params: dict[str, Any] = {
                "account": self._settings.snowflake_account,
                "user": self._settings.snowflake_user,
                "password": self._settings.snowflake_password,
                "warehouse": self._settings.snowflake_warehouse,
                "database": self._settings.snowflake_database,
                "schema": self._settings.snowflake_schema,
                "login_timeout": 15,
                "network_timeout": 30,
            }
            if self._settings.snowflake_role:
                connect_params["role"] = self._settings.snowflake_role

            conn = snowflake.connector.connect(**connect_params)
            yield conn
        except InterfaceError as e:
            logger.error("Snowflake connection failed: %s", type(e).__name__)
            raise SnowflakeError(
                "Could not connect to Snowflake. Please verify your account identifier, "
                "credentials, and network connectivity."
            ) from None
        except DatabaseError as e:
            logger.error("Snowflake database error: %s", type(e).__name__)
            raise SnowflakeError(
                "Snowflake database error. Please check your warehouse, database, "
                "schema, and role configuration."
            ) from None
        except Exception as e:
            logger.error("Unexpected Snowflake error: %s", type(e).__name__)
            raise SnowflakeError("An unexpected error occurred connecting to Snowflake.") from None
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass

    def test_connection(self) -> tuple[bool, str]:
        """Test Snowflake connectivity. Returns (success, message)."""
        if not self.is_configured:
            return False, "Snowflake credentials not configured."
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT CURRENT_VERSION()")
                version = cursor.fetchone()
                cursor.close()
                return True, f"Connected to Snowflake (v{version[0]})"
        except SnowflakeError as e:
            return False, str(e)

    def discover_schema(self, force_refresh: bool = False) -> SchemaInfo:
        """Discover tables and columns from the configured Snowflake database/schema."""
        if self._cached_schema and not force_refresh:
            return self._cached_schema

        if not self.is_configured:
            raise SnowflakeError("Snowflake credentials not configured.")

        tables: list[TableInfo] = []

        with self._get_connection() as conn:
            cursor = conn.cursor(DictCursor)

            # Get allowed databases and schemas
            allowed_dbs = self._settings.allowed_database_list
            allowed_schemas = self._settings.allowed_schema_list

            for db in allowed_dbs:
                for schema in allowed_schemas:
                    try:
                        # Discover tables
                        cursor.execute(
                            f"SHOW TABLES IN {db}.{schema}"
                        )
                        table_rows = cursor.fetchall()

                        for trow in table_rows:
                            table_name = trow.get("name", "")
                            row_count = trow.get("rows", None)
                            comment = trow.get("comment", None)

                            # Discover columns for each table
                            columns: list[ColumnInfo] = []
                            try:
                                cursor.execute(
                                    f"SHOW COLUMNS IN {db}.{schema}.{table_name}"
                                )
                                col_rows = cursor.fetchall()
                                for crow in col_rows:
                                    col_name = crow.get("column_name", "")
                                    # data_type comes as a JSON string from SHOW COLUMNS
                                    data_type_raw = crow.get("data_type", "{}")
                                    # Parse the type
                                    import json
                                    try:
                                        dt_info = json.loads(data_type_raw) if isinstance(data_type_raw, str) else data_type_raw
                                        data_type = dt_info.get("type", "UNKNOWN") if isinstance(dt_info, dict) else str(dt_info)
                                    except (json.JSONDecodeError, TypeError):
                                        data_type = str(data_type_raw)

                                    nullable = crow.get("is_nullable", "YES") == "YES"
                                    col_comment = crow.get("comment", None)
                                    columns.append(
                                        ColumnInfo(
                                            name=col_name,
                                            data_type=data_type,
                                            nullable=nullable,
                                            comment=col_comment if col_comment else None,
                                        )
                                    )
                            except Exception as e:
                                logger.warning("Could not discover columns for %s.%s.%s: %s", db, schema, table_name, type(e).__name__)

                            tables.append(
                                TableInfo(
                                    database=db,
                                    schema_name=schema,
                                    name=table_name,
                                    columns=columns,
                                    row_count=int(row_count) if row_count is not None else None,
                                    comment=comment if comment else None,
                                )
                            )
                    except ProgrammingError as e:
                        logger.warning("Could not discover schema %s.%s: %s", db, schema, type(e).__name__)
                    except Exception as e:
                        logger.warning("Unexpected error discovering %s.%s: %s", db, schema, type(e).__name__)

            cursor.close()

        from datetime import datetime
        schema_info = SchemaInfo(tables=tables, discovered_at=datetime.now().isoformat())
        self._cached_schema = schema_info
        return schema_info

    def execute_query(
        self,
        sql: str,
        timeout: int | None = None,
        max_rows: int | None = None,
    ) -> dict[str, Any]:
        """
        Execute a validated SQL query against Snowflake.

        Returns a dict with:
          - data: list of row dicts
          - columns: list of column names
          - row_count: number of rows returned
          - query_id: Snowflake query ID
          - execution_time_ms: wall-clock time
          - status: 'success' or 'error'
          - error: error message if failed
        """
        if not self.is_configured:
            raise SnowflakeError("Snowflake credentials not configured.")

        timeout = timeout or self._settings.query_timeout_seconds
        max_rows = max_rows or self._settings.max_result_rows

        with self._get_connection() as conn:
            cursor = conn.cursor(DictCursor)

            try:
                # Set statement timeout
                cursor.execute(f"ALTER SESSION SET STATEMENT_TIMEOUT_IN_SECONDS = {timeout}")

                start_time = time.time()
                cursor.execute(sql)
                rows = cursor.fetchmany(max_rows)
                elapsed_ms = (time.time() - start_time) * 1000

                query_id = cursor.sfqid
                columns = [desc[0] for desc in cursor.description] if cursor.description else []

                # Convert rows to plain dicts with serializable values
                data = []
                for row in rows:
                    clean_row = {}
                    for k, v in row.items():
                        if v is None:
                            clean_row[k] = None
                        elif isinstance(v, (int, float, str, bool)):
                            clean_row[k] = v
                        else:
                            clean_row[k] = str(v)
                    data.append(clean_row)

                return {
                    "data": data,
                    "columns": columns,
                    "row_count": len(data),
                    "total_row_count": cursor.rowcount,
                    "query_id": query_id,
                    "execution_time_ms": round(elapsed_ms, 2),
                    "status": "success",
                    "error": None,
                }

            except ProgrammingError as e:
                logger.error("Snowflake query error: %s", type(e).__name__)
                return {
                    "data": [],
                    "columns": [],
                    "row_count": 0,
                    "total_row_count": 0,
                    "query_id": getattr(cursor, "sfqid", None),
                    "execution_time_ms": 0,
                    "status": "error",
                    "error": f"Query execution failed: {self._safe_error_message(e)}",
                }
            except OperationalError as e:
                logger.error("Snowflake operational error: %s", type(e).__name__)
                return {
                    "data": [],
                    "columns": [],
                    "row_count": 0,
                    "total_row_count": 0,
                    "query_id": getattr(cursor, "sfqid", None),
                    "execution_time_ms": 0,
                    "status": "error",
                    "error": f"Query operation failed: {self._safe_error_message(e)}",
                }
            finally:
                cursor.close()

    def _safe_error_message(self, error: Exception) -> str:
        """Extract a safe error message without credentials."""
        msg = str(error)
        # Strip any credential-like patterns
        for secret in [
            self._settings.snowflake_password,
            self._settings.snowflake_user,
            self._settings.snowflake_account,
        ]:
            if secret and secret in msg:
                msg = msg.replace(secret, "***")
        return msg

    def get_schema_summary_for_prompt(self) -> str:
        """Generate a compact schema summary for inclusion in LLM prompts."""
        try:
            schema = self.discover_schema()
        except SnowflakeError:
            return "Schema unavailable — Snowflake is not connected."

        if not schema.tables:
            return "No tables found in the configured database/schema."

        lines = ["Available tables and columns:\n"]
        for table in schema.tables:
            fqn = f"{table.database}.{table.schema_name}.{table.name}"
            row_info = f" (~{table.row_count:,} rows)" if table.row_count else ""
            lines.append(f"Table: {fqn}{row_info}")
            if table.comment:
                lines.append(f"  Description: {table.comment}")
            for col in table.columns:
                null_str = ", nullable" if col.nullable else ", not null"
                comment_str = f" — {col.comment}" if col.comment else ""
                lines.append(f"  - {col.name} ({col.data_type}{null_str}){comment_str}")
            lines.append("")

        return "\n".join(lines)

    def get_table_names(self) -> list[str]:
        """Get list of fully qualified table names."""
        try:
            schema = self.discover_schema()
            return [f"{t.database}.{t.schema_name}.{t.name}" for t in schema.tables]
        except SnowflakeError:
            return []

    def get_column_names(self) -> list[str]:
        """Get list of all column names across all tables."""
        try:
            schema = self.discover_schema()
            columns = set()
            for t in schema.tables:
                for c in t.columns:
                    columns.add(c.name.upper())
            return list(columns)
        except SnowflakeError:
            return []
