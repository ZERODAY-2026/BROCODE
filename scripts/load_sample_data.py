"""
DataMind — Sample Dataset Loader

Loads the Global World Indicators dataset into Snowflake using configured credentials.
Attribution: World Bank Open Data & Our World in Data (CC-BY 4.0).
"""

import os
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.config import get_settings
from app.snowflake_adapter import SnowflakeAdapter


def main() -> None:
    settings = get_settings()

    if not settings.snowflake_configured:
        print("[!] Snowflake credentials are not configured in .env.")
        print("    Please copy .env.example to .env and configure Snowflake credentials.")
        print(f"    Alternatively, execute scripts/setup_dataset.sql directly in Snowflake Snowsight.")
        sys.exit(1)

    print(f"Connecting to Snowflake account: {settings.snowflake_account}...")
    adapter = SnowflakeAdapter(settings)
    connected, msg = adapter.test_connection()

    if not connected:
        print(f"[-] Connection failed: {msg}")
        sys.exit(1)

    print(f"[+] Successfully connected to Snowflake: {msg}")

    sql_file = Path(__file__).parent / "setup_dataset.sql"
    if not sql_file.exists():
        print(f"[-] SQL script not found at {sql_file}")
        sys.exit(1)

    sql_content = sql_file.read_text(encoding="utf-8")
    statements = [stmt.strip() for stmt in sql_content.split(";") if stmt.strip()]

    print(f"[*] Executing {len(statements)} setup statements against Snowflake...")
    for idx, stmt in enumerate(statements, 1):
        # Skip pure comments
        lines = [l for l in stmt.splitlines() if not l.strip().startswith("--")]
        clean_stmt = "\n".join(lines).strip()
        if not clean_stmt:
            continue

        try:
            adapter.execute_query(clean_stmt)
            print(f"    [{idx}/{len(statements)}] Executed statement successfully.")
        except Exception as e:
            print(f"    [!] Warning on statement {idx}: {e}")

    print("[+] Sample dataset loading complete! You can now ask questions against WORLD_INDICATORS.")


if __name__ == "__main__":
    main()
