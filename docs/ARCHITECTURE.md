# DataMind — System Architecture & Design Specification

## Overview

**DataMind** is an enterprise-grade, open-source AI data analysis platform that enables users to query structured databases in natural language. It combines **Google Gemma** for reasoning and query formulation with **Snowflake** for scalable cloud data execution, enforcing a **Zero-Trust SQL Validation Layer** to guarantee data safety.

```mermaid
flowchart TD
    User([User / Browser]) <-->|Natural Language Question / JSON Evidence| Frontend[Vite + TypeScript UI]
    Frontend <-->|REST API /api/ask| FastAPI[FastAPI Backend Server]

    subgraph Backend [DataMind Backend Pipeline]
        FastAPI --> Engine[Query Engine Orchestrator]
        Engine <-->|1. Discovered Schema & Context| SchemaCache[Schema Manager & Cache]
        Engine -->|2. Question + Schema Prompt| GemmaAdapter[Gemma Adapter (Ollama / Local / API)]
        GemmaAdapter -->|3. Candidate SQL + Interpretation| Engine
        Engine -->|4. Untrusted Candidate SQL| Validator[SQLGlot Multi-Layer Safety Validator]
        
        Validator -->|5a. Mutation / Malicious / Forbidden| SecurityReject[Safe Error / Rejected]
        Validator -->|5b. Valid Read-Only SELECT with Limits| SafeSQL[Validated SQL]
        
        SafeSQL -->|6. Execute Query| SFAdapter[Snowflake Adapter]
        SFAdapter <-->|7. Snowflake Connector (TLS)| SnowflakeCloud[(Snowflake Cloud Data Warehouse)]
        
        SFAdapter -->|8. Raw Query Records & Query ID| Engine
        Engine -->|9. Grounding & Verification| Synthesizer[Evidence & Answer Synthesizer]
        Synthesizer -->|10. Evidence Response| FastAPI
    end
```

---

## Non-Negotiable Core Flow

1. **Natural-Language Question**: The user inputs an analytical question (filtering, aggregation, ranking, comparison).
2. **Schema-Aware Gemma Interpretation**: Gemma identifies candidate tables, columns, date filters, and aggregations using the live schema.
3. **Structured Candidate SQL Generation**: Gemma emits a candidate query alongside natural language analysis steps.
4. **Zero-Trust SQL Validation (SQLGlot)**:
   - **Layer 1**: Regex dangerous keyword pre-screening (mutations, multi-statement injection).
   - **Layer 2**: Statement isolation (single statement only, comment neutralization).
   - **Layer 3**: Abstract Syntax Tree (AST) parsing via `sqlglot` with the Snowflake dialect.
   - **Layer 4**: Root expression verification (strictly `exp.Select` allowed; CTEs supported if root evaluates to SELECT).
   - **Layer 5**: Node traversal to detect nested mutations (`exp.Insert`, `exp.Update`, `exp.Delete`, `exp.Drop`, `exp.Create`, `exp.Alter`).
   - **Layer 6**: Schema-bound table verification against authorized databases and schemas.
   - **Layer 7**: Configurable row-limit enforcement (appends `LIMIT 1000` if absent).
5. **Real Snowflake Execution**: Official `snowflake-connector-python` executes the verified SQL with strict statement timeouts (30s) and parameterization.
6. **Result Verification & Grounding**: The engine cross-verifies returned numbers and columns to eliminate hallucinations.
7. **Evidence-Backed Response**: Complete audit trail returned to the frontend (executed SQL, table sources, execution duration, Snowflake Query ID, and preview table).

---

## Component Specifications

### 1. Backend (`backend/app`)
- **`main.py`**: FastAPI application exposing `/api/health`, `/api/schema`, `/api/schema/refresh`, `/api/ask`, and `/api/examples`.
- **`query_engine.py`**: Core pipeline coordinator managing intent detection, fallback cascades, execution timing, and evidence assembly.
- **`sql_validator.py`**: Multi-layer SQL parser and security sanitizer.
- **`snowflake_adapter.py`**: Thread-safe database adapter for connection pooling, schema discovery, and query execution.
- **`gemma_adapter.py`**: Resilient integration layer supporting Ollama (`gemma3:4b`, `gemma2:9b`), Google GenAI, and OpenAI-compatible endpoints with automated JSON and SQL extraction.
- **`models.py`**: Strict Pydantic models for request validation and type-safe responses.
- **`config.py`**: Centralized configuration management using Pydantic Settings and `.env`.

### 2. Frontend (`frontend/src`)
- **Vite + TypeScript**: Fast, reactive SPA built without heavyweight dependencies.
- **Vanilla CSS Design System (`index.css`)**: 1,000+ line curated dark-mode theme featuring custom CSS custom properties, responsive layout, glassmorphic headers, and micro-animations.
- **Schema Explorer**: Interactive sidebar displaying connected databases, schemas, tables, and column data types with live search filtering.
- **Dynamic SVG Chart Engine**: Client-side SVG data visualizer rendering responsive bar and comparison charts with hover tooltips and value labels.
- **Evidence Inspector**: Expandable audit accordion displaying executed SQL, copy actions, row counts, query latency, and query identifiers.
- **CSV Exporter**: Client-side CSV generation for ad-hoc analyst data downloads.

---

## Security Model

| Threat | Mitigation Mechanism |
|---|---|
| **SQL Injection (Mutating Statements)** | Blocked by regex pre-filter and AST node traversal (`exp.Delete`, `exp.Drop`, etc.). |
| **Stacked Queries (`SELECT 1; DROP TABLE`)** | Disallowed by AST parser (`len(parsed) > 1`) and semicolon isolation. |
| **Comment Evasion (`SELECT * FROM tbl -- DROP`)** | Comments stripped before safety check; AST verified on Snowflake grammar. |
| **Data Exfiltration / System Catalog Probing** | Table and database whitelist enforcement (`DATAMIND_DB.PUBLIC.*`). |
| **Denial of Service / Unbounded Queries** | Automatic row-limiting (`LIMIT 1000`) and statement execution timeout (30 seconds). |
| **Credential Exposure** | Credentials isolated to backend `.env`; never returned in API payloads or client logs. |
| **AI Hallucinations** | Grounded answer generation using verified query records; deterministic metrics. |
