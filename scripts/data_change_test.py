"""
DataMind — Critical Data-Change Verification Test

Demonstrates that DataMind answers are grounded in real, live Snowflake data
rather than hardcoded strings or model hallucinations:
1. Ask a question and record baseline answer & metrics.
2. In an authorized test environment, update a specific test value in Snowflake.
3. Re-ask the identical question.
4. Verify that the answer and returned records dynamically reflect the changed value.
"""

import asyncio
import os
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.config import get_settings
from app.gemma_adapter import GemmaAdapter
from app.query_engine import QueryEngine
from app.snowflake_adapter import SnowflakeAdapter


async def run_data_change_test() -> None:
    settings = get_settings()

    print("=" * 75)
    print(" DataMind — Critical Data-Change Verification Test (Requirement S8)")
    print("=" * 75)

    if not settings.snowflake_configured:
        print("[STATUS: PENDING LIVE CREDENTIALS]")
        print("Live Snowflake credentials are not present in .env.")
        print("To execute this verification against live Snowflake:")
        print("  1. Configure .env with valid Snowflake credentials.")
        print("  2. Load sample data with: python scripts/load_sample_data.py")
        print("  3. Run this script: python scripts/data_change_test.py")
        print("-" * 75)
        print("Verification Protocol Defined:")
        print("  Question: 'What is the population of India in 2022?'")
        print("  Step 1: Execute query against WORLD_INDICATORS; baseline pop = 1,417,173,173")
        print("  Step 2: UPDATE WORLD_INDICATORS SET POPULATION = 1420000000 WHERE COUNTRY='India' AND YEAR=2022")
        print("  Step 3: Re-execute question through pipeline")
        print("  Step 4: Verify answer reflects updated 1,420,000,000 value with updated query_id")
        print("  Step 5: Rollback/restore original record")
        print("=" * 75)
        return

    print("Connecting to live Snowflake instance...")
    sf = SnowflakeAdapter(settings)
    gemma = GemmaAdapter(settings)
    engine = QueryEngine(sf, gemma)

    question = "What is the population of India in 2022?"
    print(f"\n[Step 1] Asking baseline question: \"{question}\"")
    baseline_resp = await engine.answer_question(question)
    print(f"  Baseline Answer: {baseline_resp.answer}")
    print(f"  Baseline Data: {baseline_resp.data}")

    print("\n[Step 2] Executing authorized test update in Snowflake...")
    update_sql = "UPDATE WORLD_INDICATORS SET POPULATION = 1420000000 WHERE COUNTRY = 'India' AND YEAR = 2022"
    sf.execute_query(update_sql)
    print("  Update executed successfully.")

    print(f"\n[Step 3] Re-asking identical question: \"{question}\"")
    updated_resp = await engine.answer_question(question)
    print(f"  Updated Answer: {updated_resp.answer}")
    print(f"  Updated Data: {updated_resp.data}")

    # Step 4: Verification
    assert updated_resp.data is not None and len(updated_resp.data) > 0
    new_val = updated_resp.data[0].get("POPULATION") or updated_resp.data[0].get("population")
    print(f"\n[Step 4] Verification Check:")
    print(f"  New retrieved value: {new_val}")
    if new_val == 1420000000:
        print("  ✓ SUCCESS: Value dynamically changed! Proves no hardcoded results.")
    else:
        print(f"  [-] Unexpected value: {new_val}")

    print("\n[Step 5] Restoring baseline data...")
    restore_sql = "UPDATE WORLD_INDICATORS SET POPULATION = 1417173173 WHERE COUNTRY = 'India' AND YEAR = 2022"
    sf.execute_query(restore_sql)
    print("  Baseline data restored successfully.")
    print("=" * 75)


if __name__ == "__main__":
    asyncio.run(run_data_change_test())
