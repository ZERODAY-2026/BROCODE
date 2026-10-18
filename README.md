# 🧠 DataMind — Talk to Your Data

> **PS1 | ZeroDay OSS Hacktoberfest 2026 | IIIT Dharwad**  
> AI-powered natural-language data analysis agent using **Google Gemma** and **Snowflake**, fortified with a **Zero-Trust SQL Validation Layer**.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-009688.svg)](https://fastapi.tiangolo.com)
[![Snowflake](https://img.shields.io/badge/Snowflake-Connector%203.8+-29B5E8.svg)](https://www.snowflake.com/)
[![Google Gemma](https://img.shields.io/badge/Google%20Gemma-Gemma%203%20%2F%202-4285F4.svg)](https://ai.google.dev/gemma)
[![Vite + TS](https://img.shields.io/badge/Frontend-Vite%20%7C%20TypeScript-646CFF.svg)](https://vitejs.dev/)
[![Tests Passing](https://img.shields.io/badge/tests-79%20passed-brightgreen.svg)]()

---

## 🌟 Executive Summary

**DataMind** is an open-source analytical platform that empowers non-technical and technical users alike to converse with structured cloud datasets using natural language. Rather than relying on simulated queries, hardcoded dictionaries, or hallucinated numbers, DataMind executes a strict **Zero-Trust Analytical Pipeline**:

$$\text{Natural-Language Question} \longrightarrow \text{Gemma Schema Reasoner} \longrightarrow \text{SQLGlot Multi-Layer Validator} \longrightarrow \text{Snowflake Cloud Warehouse} \longrightarrow \text{Evidence-Backed Grounded Synthesis}$$

Every claim, numeric metric, and percentage returned is verified against real data queried at question time from Snowflake, accompanied by a complete audit trail (executed SQL, query latency, Snowflake Query ID, and data preview).

---

## 🏗️ System Architecture

```mermaid
flowchart TD
    User([User / Analyst]) <-->|Natural Language Question| UI[DataMind Modern Web UI]
    UI <-->|REST API /api/ask| API[FastAPI Backend Server]

    subgraph CoreEngine [DataMind Core Engine]
        API --> Engine[Query Engine Orchestrator]
        Engine <-->|Live Discovered Schema| SchemaMgr[Snowflake Schema Explorer]
        Engine -->|Prompt: Question + Live Schema| GemmaAdapter[Gemma Adapter (Ollama / Local / API)]
        GemmaAdapter -->|Candidate SQL + Reasoning Plan| Engine
        
        Engine -->|Candidate SQL| Validator{SQLGlot Safety Validator}
        
        Validator -->|Mutations / Multiple Statements / Prohibited DDL| Reject[🚫 Safe Rejection & Error Notice]
        Validator -->|Validated Read-Only SELECT with Limits| SafeSQL[✅ Safe SQL Query]
        
        SafeSQL -->|Query Execution| SFConn[Snowflake Python Connector]
        SFConn <-->|TLS 1.3 / Warehouse Execution| SF[(Snowflake Cloud Warehouse)]
        
        SFConn -->|Real Records & Query ID| Engine
        Engine -->|Data + Grounding Check| Synthesizer[Evidence & Answer Synthesizer]
        Synthesizer -->|Inspectable Evidence + Preview| API
    end
```

---

## ✨ Key Features (Requirements M1–M8)

| Feature | Description |
|---|---|
| **M1: Natural-Language Interaction** | Query structured datasets without writing SQL. Full support for filtering, ranking, aggregation, multi-year comparisons, and sorting. |
| **M2: Real Data at Question Time** | Zero hardcoding or fake mocks. Queries run against live Snowflake tables at query time. |
| **M3: Grounded Answers** | Answers are mathematically derived from verified query records; zero hallucinations of numbers, dates, or trends. |
| **M4: Transparent Explanations** | Explains what was measured, which filters were applied, and assumptions made. |
| **M5: Inspectable Evidence** | Users can inspect proposed SQL vs. executed SQL, referenced tables/columns, execution duration (ms), row count, and Snowflake Query ID. |
| **M6: Ambiguity & Error Handling** | Detects underspecified questions (e.g. "show best countries") and prompts for clarification; gracefully handles missing columns, empty results, and timeouts. |
| **M7: Genuine Gemma & Snowflake Roles** | Gemma performs real reasoning (schema resolution, SQL construction, grounding); Snowflake executes data retrieval and aggregation. |
| **M8: Reproducible & Open-Source** | Fully containerizable, verified test suite (79 unit/safety/pipeline tests), sample dataset DDL/DML, and MIT License. |

---

## 🛡️ Zero-Trust SQL Safety Guarantee

DataMind treats all model-generated SQL as **untrusted user input**:

1. **Layer 1: Dangerous Keyword Pre-screening**: Regular expression filters block destructive verbs (`INSERT`, `UPDATE`, `DELETE`, `DROP`, `ALTER`, `CREATE`, `TRUNCATE`, `GRANT`, `REVOKE`, etc.).
2. **Layer 2: Statement Isolation**: Blocks multiple stacked statements (`;` injection) while safely allowing comments and string literals.
3. **Layer 3: Abstract Syntax Tree (AST) Parsing**: Parsed using `sqlglot` under the Snowflake dialect.
4. **Layer 4: Root Expression Enforcement**: Strictly `exp.Select` allowed (CTEs permitted only if the root expression resolves to a SELECT).
5. **Layer 5: AST Mutation Traversal**: Deep AST walk to detect embedded mutation expressions.
6. **Layer 6: Schema Whitelist Verification**: Verifies referenced tables against permitted databases and schemas (`DATAMIND_DB.PUBLIC.*`).
7. **Layer 7: Automatic Row Capping**: Injects `LIMIT 1000` to prevent unbounded query costs or warehouse memory exhaustion.

---

## 📊 Dataset Specification

DataMind includes a verified benchmark dataset: **`WORLD_INDICATORS`** (2018–2022).
- **Origin**: World Bank Open Data & Our World in Data.
- **Licence**: Creative Commons Attribution 4.0 International ([CC-BY 4.0](https://creativecommons.org/licenses/by/4.0/)).
- **Attributes**: `COUNTRY`, `COUNTRY_CODE`, `CONTINENT`, `YEAR`, `GDP_USD`, `POPULATION`, `LIFE_EXPECTANCY`, `CO2_EMISSIONS_PER_CAPITA`, `INTERNET_USERS_PCT`.

---

## 🚀 Quick Start Guide

### 1. Prerequisites
- Python 3.10+
- Node.js 18+ and npm
- Ollama with Gemma (or access to Google GenAI)
- Snowflake Account (or Snowflake Trial)

### 2. Backend Setup
```bash
# Clone the repository
git clone https://github.com/ZERODAY-2026/BROCODE.git
cd BROCODE

# Install backend dependencies
cd backend
pip install -r requirements.txt

# Configure environment variables
cp ../.env.example ../.env
# Edit .env with your Snowflake credentials and Gemma settings
```

### 3. Gemma Setup (Local Ollama)
```bash
# Install and run Ollama
ollama run gemma3:4b
# Or gemma2:9b
```

### 4. Snowflake Setup & Dataset Loading
Execute [`scripts/setup_dataset.sql`](scripts/setup_dataset.sql) in Snowflake Snowsight, or run:
```bash
python scripts/load_sample_data.py
```

### 5. Frontend Setup
```bash
cd ../frontend
npm install
npm run dev
```
Open [http://localhost:5173](http://localhost:5173) in your browser.

### 6. Run the Backend Server
```bash
cd ../backend
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

---

## 🧪 Testing & Verification

Run the full automated test suite (79 tests covering models, SQL safety, Gemma adapter, query engine, and API endpoints):

```bash
# Run backend tests
python -m pytest backend/tests -v
```

Run the independent correctness evaluation benchmark:
```bash
python scripts/evaluate_correctness.py
```

Run the critical data-change test (verifies results update when Snowflake data updates):
```bash
python scripts/data_change_test.py
```

---

## 📁 Repository Structure

```
BROCODE/
├── .env.example              # Sample environment configuration template
├── .gitignore                # Git ignore rules (secrets, venvs, dist)
├── LICENSE                   # Open-source MIT License
├── README.md                 # Master project documentation
├── backend/
│   ├── app/
│   │   ├── config.py         # Pydantic environment configuration
│   │   ├── gemma_adapter.py  # Gemma reasoning & SQL generation adapter
│   │   ├── main.py           # FastAPI application endpoints & lifespan
│   │   ├── models.py         # Type-safe Pydantic request/response schemas
│   │   ├── query_engine.py   # Core question-to-evidence pipeline coordinator
│   │   ├── snowflake_adapter.py # Snowflake connector & schema explorer
│   │   └── sql_validator.py  # Zero-Trust SQLGlot AST safety validator
│   ├── pyproject.toml        # Project metadata
│   ├── requirements.txt      # Python dependencies
│   └── tests/
│       ├── test_api.py       # FastAPI endpoint tests
│       ├── test_gemma.py     # Gemma prompt & JSON parsing tests
│       ├── test_integration.py # Live integration tests (Snowflake/Gemma)
│       ├── test_models.py    # Schema & Pydantic validation tests
│       ├── test_query_engine.py # End-to-end pipeline orchestration tests
│       └── test_sql_validator.py # Multi-layer SQL security & injection tests
├── frontend/
│   ├── index.html            # Web entry point
│   ├── package.json          # Frontend dependencies & scripts
│   ├── tsconfig.json         # TypeScript configuration
│   ├── vite.config.ts        # Vite configuration with API proxy
│   └── src/
│       ├── index.css         # Complete 1,000+ line dark-mode design system
│       └── main.ts           # Reactive TypeScript application & SVG charts
├── docs/
│   ├── ARCHITECTURE.md       # In-depth architectural & security specification
│   ├── DATASET.md            # Dataset specification, attribution, & DDL
│   └── evaluation_results.json # Automated evaluation benchmark output
└── scripts/
    ├── data_change_test.py   # Live data-change verification script
    ├── evaluate_correctness.py # Automated correctness benchmark runner
    ├── load_sample_data.py   # Automated Snowflake data loader
    └── setup_dataset.sql     # Standalone Snowflake worksheet DDL/DML script
```

---

## 📄 Open-Source Licence & Attribution

- **Application Code**: Licensed under the [MIT License](LICENSE).
- **Dataset**: [World Bank Open Data](https://data.worldbank.org) and [Our World in Data](https://ourworldindata.org) ([CC-BY 4.0](https://creativecommons.org/licenses/by/4.0/)).
- **Model**: [Google Gemma](https://ai.google.dev/gemma) is subject to the [Gemma Terms of Use](https://ai.google.dev/gemma/terms).

---

*Built with passion for ZeroDay OSS Hacktoberfest 2026 | IIIT Dharwad.*
