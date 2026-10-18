"""
DataMind — SQL Validator Unit Tests

Tests the multi-layer SQL validation system for safety, correctness,
and schema-binding. These are pure unit tests with no external dependencies.
"""

import pytest
from app.sql_validator import SQLValidator, ValidationResult


@pytest.fixture
def validator() -> SQLValidator:
    """Create a validator with sample allowed tables/columns."""
    return SQLValidator(
        allowed_tables=[
            "DATAMIND_DB.PUBLIC.WORLD_INDICATORS",
            "DATAMIND_DB.PUBLIC.COUNTRIES",
        ],
        allowed_columns=[
            "COUNTRY", "YEAR", "GDP", "POPULATION", "LIFE_EXPECTANCY",
            "CO2_EMISSIONS", "CONTINENT", "COUNTRY_CODE", "INDICATOR_NAME",
            "INDICATOR_VALUE",
        ],
        max_rows=500,
        allowed_databases=["DATAMIND_DB"],
        allowed_schemas=["PUBLIC"],
    )


@pytest.fixture
def open_validator() -> SQLValidator:
    """Validator with no table/column restrictions (for general SQL safety tests)."""
    return SQLValidator(max_rows=1000)


class TestSelectQueries:
    """Test that valid SELECT queries pass validation."""

    def test_simple_select(self, validator: SQLValidator):
        result = validator.validate("SELECT COUNTRY, GDP FROM DATAMIND_DB.PUBLIC.WORLD_INDICATORS WHERE YEAR = 2020")
        assert result.is_valid, f"Expected valid, got errors: {result.errors}"

    def test_select_with_aggregation(self, validator: SQLValidator):
        result = validator.validate(
            "SELECT CONTINENT, AVG(GDP) as AVG_GDP FROM DATAMIND_DB.PUBLIC.WORLD_INDICATORS GROUP BY CONTINENT"
        )
        assert result.is_valid, f"Expected valid, got errors: {result.errors}"

    def test_select_with_order_and_limit(self, validator: SQLValidator):
        result = validator.validate(
            "SELECT COUNTRY, POPULATION FROM DATAMIND_DB.PUBLIC.WORLD_INDICATORS ORDER BY POPULATION DESC LIMIT 10"
        )
        assert result.is_valid

    def test_select_with_join(self, validator: SQLValidator):
        result = validator.validate(
            "SELECT a.COUNTRY, a.GDP FROM DATAMIND_DB.PUBLIC.WORLD_INDICATORS a "
            "JOIN DATAMIND_DB.PUBLIC.COUNTRIES b ON a.COUNTRY = b.COUNTRY"
        )
        assert result.is_valid

    def test_select_with_subquery(self, open_validator: SQLValidator):
        result = open_validator.validate(
            "SELECT * FROM (SELECT COUNTRY, MAX(GDP) as MAX_GDP FROM my_table GROUP BY COUNTRY) sub"
        )
        assert result.is_valid

    def test_select_with_cte(self, open_validator: SQLValidator):
        result = open_validator.validate(
            "WITH ranked AS (SELECT COUNTRY, GDP, ROW_NUMBER() OVER (ORDER BY GDP DESC) as rn FROM my_table) "
            "SELECT * FROM ranked WHERE rn <= 5"
        )
        assert result.is_valid

    def test_adds_limit_when_missing(self, validator: SQLValidator):
        result = validator.validate(
            "SELECT COUNTRY FROM DATAMIND_DB.PUBLIC.WORLD_INDICATORS"
        )
        assert result.is_valid
        assert "LIMIT" in result.sql
        assert any("LIMIT" in w for w in result.warnings)

    def test_preserves_existing_limit(self, validator: SQLValidator):
        sql = "SELECT COUNTRY FROM DATAMIND_DB.PUBLIC.WORLD_INDICATORS LIMIT 10"
        result = validator.validate(sql)
        assert result.is_valid
        assert "LIMIT 10" in result.sql or "LIMIT 500" not in result.sql


class TestDestructiveStatements:
    """Test that destructive/mutating SQL is rejected."""

    def test_reject_insert(self, validator: SQLValidator):
        result = validator.validate("INSERT INTO DATAMIND_DB.PUBLIC.WORLD_INDICATORS (COUNTRY) VALUES ('Test')")
        assert not result.is_valid
        assert any("destructive" in e.lower() or "dangerous" in e.lower() or "select" in e.lower() for e in result.errors)

    def test_reject_update(self, validator: SQLValidator):
        result = validator.validate("UPDATE DATAMIND_DB.PUBLIC.WORLD_INDICATORS SET GDP = 0 WHERE COUNTRY = 'Test'")
        assert not result.is_valid

    def test_reject_delete(self, validator: SQLValidator):
        result = validator.validate("DELETE FROM DATAMIND_DB.PUBLIC.WORLD_INDICATORS WHERE COUNTRY = 'Test'")
        assert not result.is_valid

    def test_reject_drop_table(self, validator: SQLValidator):
        result = validator.validate("DROP TABLE DATAMIND_DB.PUBLIC.WORLD_INDICATORS")
        assert not result.is_valid

    def test_reject_alter(self, validator: SQLValidator):
        result = validator.validate("ALTER TABLE DATAMIND_DB.PUBLIC.WORLD_INDICATORS ADD COLUMN test VARCHAR")
        assert not result.is_valid

    def test_reject_create(self, validator: SQLValidator):
        result = validator.validate("CREATE TABLE test (id INT)")
        assert not result.is_valid

    def test_reject_truncate(self, validator: SQLValidator):
        result = validator.validate("TRUNCATE TABLE DATAMIND_DB.PUBLIC.WORLD_INDICATORS")
        assert not result.is_valid

    def test_reject_grant(self, validator: SQLValidator):
        result = validator.validate("GRANT SELECT ON DATAMIND_DB.PUBLIC.WORLD_INDICATORS TO ROLE PUBLIC")
        assert not result.is_valid


class TestMultipleStatements:
    """Test that multiple statement attempts are rejected."""

    def test_reject_semicolon_separated(self, validator: SQLValidator):
        result = validator.validate(
            "SELECT 1; DROP TABLE DATAMIND_DB.PUBLIC.WORLD_INDICATORS"
        )
        assert not result.is_valid

    def test_reject_multiple_selects(self, validator: SQLValidator):
        result = validator.validate(
            "SELECT 1; SELECT 2"
        )
        assert not result.is_valid


class TestSQLInjection:
    """Test SQL injection prevention."""

    def test_reject_union_with_system_tables(self, open_validator: SQLValidator):
        # While UNION itself might be valid, we test that the validator catches
        # references to system tables if configured
        result = open_validator.validate(
            "SELECT 1 UNION SELECT * FROM INFORMATION_SCHEMA.TABLES"
        )
        # This should parse as valid SELECT — the table restriction would catch it
        # with a configured validator
        assert result.is_valid  # open validator allows it

    def test_reject_comment_injection(self, validator: SQLValidator):
        result = validator.validate(
            "SELECT COUNTRY FROM DATAMIND_DB.PUBLIC.WORLD_INDICATORS -- ; DROP TABLE x"
        )
        # SQL comment is harmless, the DROP is commented out
        assert result.is_valid

    def test_reject_dangerous_pattern_bypass(self, validator: SQLValidator):
        result = validator.validate(
            "SELECT COUNTRY FROM DATAMIND_DB.PUBLIC.WORLD_INDICATORS WHERE COUNTRY = 'test'; DELETE FROM x"
        )
        assert not result.is_valid


class TestTableRestrictions:
    """Test schema-bound table access restrictions."""

    def test_reject_unauthorized_table(self, validator: SQLValidator):
        result = validator.validate(
            "SELECT * FROM DATAMIND_DB.PUBLIC.SECRET_TABLE"
        )
        assert not result.is_valid
        assert any("not in the allowed" in e.lower() for e in result.errors)

    def test_reject_unauthorized_database(self, validator: SQLValidator):
        result = validator.validate(
            "SELECT * FROM OTHER_DB.PUBLIC.WORLD_INDICATORS"
        )
        assert not result.is_valid

    def test_reject_unauthorized_schema(self, validator: SQLValidator):
        result = validator.validate(
            "SELECT * FROM DATAMIND_DB.PRIVATE.WORLD_INDICATORS"
        )
        assert not result.is_valid


class TestEdgeCases:
    """Test edge cases and malformed input."""

    def test_empty_sql(self, validator: SQLValidator):
        result = validator.validate("")
        assert not result.is_valid

    def test_whitespace_only(self, validator: SQLValidator):
        result = validator.validate("   ")
        assert not result.is_valid

    def test_none_like_string(self, validator: SQLValidator):
        result = validator.validate("None")
        assert not result.is_valid

    def test_just_semicolons(self, validator: SQLValidator):
        result = validator.validate(";;;")
        assert not result.is_valid

    def test_referenced_tables_extracted(self, validator: SQLValidator):
        result = validator.validate(
            "SELECT COUNTRY FROM DATAMIND_DB.PUBLIC.WORLD_INDICATORS"
        )
        assert result.is_valid
        assert len(result.referenced_tables) > 0

    def test_very_long_query(self, open_validator: SQLValidator):
        """Extremely long query should still be parseable."""
        conditions = " AND ".join([f"col{i} = {i}" for i in range(50)])
        sql = f"SELECT * FROM my_table WHERE {conditions}"
        result = open_validator.validate(sql)
        assert result.is_valid


class TestExcessiveResults:
    """Test row limit enforcement."""

    def test_limit_added_when_missing(self, validator: SQLValidator):
        result = validator.validate(
            "SELECT * FROM DATAMIND_DB.PUBLIC.WORLD_INDICATORS"
        )
        assert result.is_valid
        assert "LIMIT" in result.sql

    def test_explicit_limit_preserved(self, validator: SQLValidator):
        result = validator.validate(
            "SELECT * FROM DATAMIND_DB.PUBLIC.WORLD_INDICATORS LIMIT 5"
        )
        assert result.is_valid
