"""Phase 2 staging: OpportunityFieldHistory stage transitions → Lakehouse.

Adds `f_stage_transition` to lkh_sales_kpis_rw. Each row = one stage change
with derived `days_in_prior_stage` (lag-window from the prior transition
on the same opportunity).

Unlocks 2 HIGH-impact RW KPIs:
  - stage_conversion (target: >70% stage-to-stage)
  - time_in_stage (target: baseline & optimize)

Run after sf_to_fabric_rw.py (Phase 1) — same Lakehouse target.

Usage:
    python3 scripts/sales/sf_to_fabric_rw_phase2.py
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

from scripts.sales.rw_stage_order import (
    parse_stage_label,
    stage_display_for_label,
    stage_order_for_label,
)

WORKSPACE_ID = "b66233d5-9d4a-44ba-89a8-b70206d98ae7"
LAKEHOUSE_ID = "50f1721e-6b2e-44db-a1a7-7b8209c7a77b"  # lkh_sales_kpis_rw
SF_ORG = "apro@simcorp.com"

ONELAKE_BASE = f"abfss://{WORKSPACE_ID}@onelake.dfs.fabric.microsoft.com/{LAKEHOUSE_ID}/Tables"

SOQL_OFH = """
SELECT OpportunityId, Field, OldValue, NewValue, CreatedDate
FROM OpportunityFieldHistory
WHERE Field='StageName' AND (CreatedDate = LAST_N_FISCAL_YEARS:3 OR CreatedDate = THIS_FISCAL_YEAR)
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


def _parse_stage(s: str | None) -> tuple[int | None, str | None]:
    """Parse '5 - Preferred' → (5, 'Preferred'). Returns (None, raw) if pattern doesn't match."""
    if s is None or pd.isna(s):
        return (None, None)
    return parse_stage_label(s)


def transform(stage: pathlib.Path) -> pd.DataFrame:
    con = duckdb.connect(":memory:")
    con.execute(f"CREATE TABLE raw_ofh AS SELECT * FROM read_csv_auto('{stage / 'ofh.csv'}')")
    df = con.execute("""
        SELECT
            "OpportunityId" as opp_id,
            "OldValue" as from_stage_raw,
            "NewValue" as to_stage_raw,
            CAST("CreatedDate" AS TIMESTAMP) as transition_at,
            LAG(CAST("CreatedDate" AS TIMESTAMP)) OVER (
                PARTITION BY "OpportunityId" ORDER BY "CreatedDate"
            ) as prior_transition_at,
            EXTRACT(EPOCH FROM
                CAST("CreatedDate" AS TIMESTAMP)
                - LAG(CAST("CreatedDate" AS TIMESTAMP)) OVER (
                    PARTITION BY "OpportunityId" ORDER BY "CreatedDate"
                )
            ) / 86400.0 as days_in_prior_stage
        FROM raw_ofh
        ORDER BY opp_id, transition_at
    """).fetch_df()

    # Parse stage numbers off "N - Name"
    parsed_from = df["from_stage_raw"].apply(_parse_stage)
    parsed_to = df["to_stage_raw"].apply(_parse_stage)
    df["from_stage_num"] = [p[0] for p in parsed_from]
    df["from_stage_name"] = [p[1] for p in parsed_from]
    df["to_stage_num"] = [p[0] for p in parsed_to]
    df["to_stage_name"] = [p[1] for p in parsed_to]
    df["from_stage_order"] = df["from_stage_raw"].apply(stage_order_for_label).astype("int64")
    df["to_stage_order"] = df["to_stage_raw"].apply(stage_order_for_label).astype("int64")
    df["from_stage_display"] = df["from_stage_raw"].apply(stage_display_for_label)
    df["to_stage_display"] = df["to_stage_raw"].apply(stage_display_for_label)

    # Direction: forward if to>from, backward if to<from, lateral otherwise (e.g. closing)
    def _direction(row):
        f, t = row["from_stage_num"], row["to_stage_num"]
        if f is None or t is None:
            return "unknown"
        if t > f:
            return "forward"
        if t < f:
            return "backward"
        return "lateral"

    df["direction"] = df.apply(_direction, axis=1)
    return df


def write_to_onelake(df: pd.DataFrame) -> None:
    cred = AzureCliCredential()
    token = cred.get_token("https://storage.azure.com/.default").token
    storage_options = {"bearer_token": token, "use_fabric_endpoint": "true"}
    write_deltalake(
        f"{ONELAKE_BASE}/f_stage_transition",
        df,
        mode="overwrite",
        schema_mode="overwrite",
        storage_options=storage_options,
    )
    print(f"  f_stage_transition: {len(df):,} rows -> {ONELAKE_BASE}/f_stage_transition")


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        stage = pathlib.Path(tmp)
        print("Step 1/3: SF query OpportunityFieldHistory (stage changes, 3 FY)...")
        n = _run_soql(SOQL_OFH, stage / "ofh.csv")
        print(f"  raw OFH rows: {n:,}")

        print("\nStep 2/3: derive stage transitions with days-in-prior-stage...")
        df = transform(stage)
        print(f"  f_stage_transition: {len(df):,} rows")
        print("  direction split:")
        print(df["direction"].value_counts().to_string())

        print("\nStep 3/3: write Delta table to OneLake...")
        write_to_onelake(df)

    print("\ndone. Run rw_push_semantic_model.py to wire f_stage_transition into the model.")


if __name__ == "__main__":
    main()
