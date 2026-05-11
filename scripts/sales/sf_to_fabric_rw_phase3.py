"""Phase 3 staging: ForecastCategoryName transitions → Lakehouse.

Adds `f_forecast_transition` to lkh_sales_kpis_rw. Mirror of Phase 2 (stage
transitions) but for forecast-category moves (Pipeline → Commit, Commit →
Closed, etc.).

Unlocks measures:
  - Commit Win Rate (of opps that entered Commit, % won)
  - Forecast Category Slips (Commit → Pipeline = downgrade)
  - Avg Days in Commit
  - (Approximates the RW KPI `forecast_accuracy ±5%` target — true forecast
    accuracy needs ForecastingItem snapshots which is Phase 3.5 work.)

Note: SimCorp uses Apttus for Commercial Approval, not SF native ApprovalProcess
(ProcessInstance returned 0 rows for our opps). That's deferred to a separate
phase that probes Apttus_Proposal__c / Apttus_Config__c custom objects.

Usage:
    python3 scripts/sales/sf_to_fabric_rw_phase3.py
"""

from __future__ import annotations

import pathlib
import subprocess
import sys
import tempfile

import duckdb
import pandas as pd
from azure.identity import AzureCliCredential
from deltalake import write_deltalake

WORKSPACE_ID = "b66233d5-9d4a-44ba-89a8-b70206d98ae7"
LAKEHOUSE_ID = "50f1721e-6b2e-44db-a1a7-7b8209c7a77b"
SF_ORG = "apro@simcorp.com"

ONELAKE_BASE = f"abfss://{WORKSPACE_ID}@onelake.dfs.fabric.microsoft.com/{LAKEHOUSE_ID}/Tables"

SOQL_FORECAST_OFH = """
SELECT OpportunityId, Field, OldValue, NewValue, CreatedDate
FROM OpportunityFieldHistory
WHERE Field='ForecastCategoryName'
  AND (CreatedDate = LAST_N_FISCAL_YEARS:3 OR CreatedDate = THIS_FISCAL_YEAR)
ORDER BY OpportunityId, CreatedDate ASC
"""


def _run_soql(query: str, target_csv: pathlib.Path) -> int:
    proc = subprocess.run(
        ["sf", "data", "query", "-o", SF_ORG, "-q", " ".join(query.split()), "-r", "csv"],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        print("  SF query failed:", proc.stderr[:500], file=sys.stderr)
        raise RuntimeError("sf data query failed")
    target_csv.write_text(proc.stdout)
    return max(0, sum(1 for _ in proc.stdout.splitlines()) - 1)


def transform(stage: pathlib.Path) -> pd.DataFrame:
    con = duckdb.connect(":memory:")
    con.execute(
        f"CREATE TABLE raw_ofh AS SELECT * FROM read_csv_auto('{stage / 'forecast_ofh.csv'}')"
    )
    df = con.execute("""
        SELECT
            "OpportunityId" as opp_id,
            "OldValue" as from_category,
            "NewValue" as to_category,
            CAST("CreatedDate" AS TIMESTAMP) as transition_at,
            LAG(CAST("CreatedDate" AS TIMESTAMP)) OVER (
                PARTITION BY "OpportunityId" ORDER BY "CreatedDate"
            ) as prior_transition_at,
            EXTRACT(EPOCH FROM
                CAST("CreatedDate" AS TIMESTAMP)
                - LAG(CAST("CreatedDate" AS TIMESTAMP)) OVER (
                    PARTITION BY "OpportunityId" ORDER BY "CreatedDate"
                )
            ) / 86400.0 as days_in_prior_category
        FROM raw_ofh
        WHERE COALESCE("OldValue", '') <> 'Omitted'
          AND COALESCE("NewValue", '') <> 'Omitted'
        ORDER BY opp_id, transition_at
    """).fetch_df()

    # Defensive repeat of the SQL filter: Omitted is a hygiene bucket, not a
    # committed forecast category, so transitions into or out of Omitted must not
    # inflate slip/upgrade counts or days-in-category windows.
    df = df[
        ~df["from_category"].isin({"Omitted"})
        & ~df["to_category"].isin({"Omitted"})
    ].copy()

    # Forecast category ranking: lower number = more committed (closer to revenue)
    # Pipeline (4) > Best Case (3) > Commit (2) > Closed (1). Omitted is removed above.
    rank_map = {
        "Closed": 1,
        "Commit": 2,
        "Best Case": 3,
        "Pipeline": 4,
        "Forecast": 2,  # legacy alias, treat as Commit
    }
    df["from_rank"] = df["from_category"].map(rank_map).fillna(0)
    df["to_rank"] = df["to_category"].map(rank_map).fillna(0)

    def _direction(row):
        if row["from_rank"] == 0 or row["to_rank"] == 0:
            return "unknown"
        if row["to_rank"] < row["from_rank"]:
            return "upgrade"  # moved closer to closed (e.g. Pipeline→Commit)
        if row["to_rank"] > row["from_rank"]:
            return "slip"  # downgrade (e.g. Commit→Pipeline)
        return "lateral"

    df["direction"] = df.apply(_direction, axis=1)
    return df


def write_to_onelake(df: pd.DataFrame) -> None:
    cred = AzureCliCredential()
    token = cred.get_token("https://storage.azure.com/.default").token
    storage_options = {"bearer_token": token, "use_fabric_endpoint": "true"}
    write_deltalake(
        f"{ONELAKE_BASE}/f_forecast_transition",
        df,
        mode="overwrite",
        storage_options=storage_options,
    )
    print(f"  f_forecast_transition: {len(df):,} rows -> {ONELAKE_BASE}/f_forecast_transition")


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        stage = pathlib.Path(tmp)
        print("Step 1/3: SF query OpportunityFieldHistory (ForecastCategory)...")
        n = _run_soql(SOQL_FORECAST_OFH, stage / "forecast_ofh.csv")
        print(f"  raw OFH rows: {n:,}")

        print("\nStep 2/3: derive forecast-category transitions...")
        df = transform(stage)
        print(f"  f_forecast_transition: {len(df):,} rows")
        print("  direction split:")
        print(df["direction"].value_counts().to_string())

        print("\nStep 3/3: write Delta table to OneLake...")
        write_to_onelake(df)

    print("\ndone. Run rw_push_semantic_model.py to wire f_forecast_transition.")


if __name__ == "__main__":
    main()
