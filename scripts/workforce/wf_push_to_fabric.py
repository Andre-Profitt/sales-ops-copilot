"""Stage the RW (Reps Working) workforce KPIs from the local DuckDB store
into the Fabric Lakehouse `lkh_workforce_rw` as Delta tables.

Re-run nightly (Phase 2) after wf.duckdb is refreshed from live SF.

Output URI:
  abfss://<WORKSPACE_ID>@onelake.dfs.fabric.microsoft.com/<LAKEHOUSE_ID>/Tables/<table>

Auth: AzureCliCredential — assumes `az login` as APRO@simcorp.com.

Usage:
  python3 scripts/workforce/wf_push_to_fabric.py
"""

from __future__ import annotations

import pathlib

import duckdb
from azure.identity import AzureCliCredential
from deltalake import write_deltalake

# Targets
WORKSPACE_ID = "b66233d5-9d4a-44ba-89a8-b70206d98ae7"  # Salesforce Analytics - Sales Manager
LAKEHOUSE_ID = "34ea3a8c-6493-45ab-ab28-1d14bed9987f"  # lkh_workforce_rw

DB_PATH = pathlib.Path.home() / "code/apps/sales-ops-copilot/workforce/state/wf.duckdb"

# Excel-serial date anchor: serial N -> 1899-12-30 + N days
EXCEL_ANCHOR = "DATE '1899-12-30'"


def _select_clauses() -> dict[str, str]:
    """Cast queries that promote the all-VARCHAR DuckDB store to typed columns."""
    return {
        "weekly_person_kpis": f"""
            select
                person_id, canonical_name,
                ({EXCEL_ANCHOR} + INTERVAL (CAST(event_week_start AS BIGINT)) DAY) as event_week_start,
                event_week,
                CAST(actions AS DOUBLE) as actions,
                CAST(actions_adj AS DOUBLE) as actions_adj,
                CAST(unique_records AS DOUBLE) as unique_records,
                CAST(effort_units AS DOUBLE) as effort_units,
                CAST(effort_adj AS DOUBLE) as effort_adj,
                CAST(availability_factor AS DOUBLE) as availability_factor,
                CAST(available_days AS DOUBLE) as available_days,
                CAST(leave_days AS DOUBLE) as leave_days,
                CAST(actions_adj_per_avail_week AS DOUBLE) as actions_adj_per_avail_week,
                CAST(effort_adj_per_avail_week AS DOUBLE) as effort_adj_per_avail_week,
                CAST(utilization_index_p75 AS DOUBLE) as utilization_index_p75,
                CAST(utilization_p75_4w_avg AS DOUBLE) as utilization_p75_4w_avg
            from weekly_person_kpis
        """,
        "coverage_concentration": """
            select segment, process_family,
                CAST(total_effort AS DOUBLE) as total_effort,
                CAST(effective_contributors AS DOUBLE) as effective_contributors,
                CAST(top1_share AS DOUBLE) as top1_share,
                top1_person_name,
                CAST(top2_share AS DOUBLE) as top2_share
            from coverage_concentration
        """,
        "dim_people": "select * from dim_people",
        "anomalies_log": "select * from anomalies_log",
        "forecast_output": "select * from forecast_output",
        "weekly_team_kpis": "select * from weekly_team_kpis",
    }


def main() -> None:
    cred = AzureCliCredential()
    token = cred.get_token("https://storage.azure.com/.default").token
    storage_options = {"bearer_token": token, "use_fabric_endpoint": "true"}

    base = f"abfss://{WORKSPACE_ID}@onelake.dfs.fabric.microsoft.com/{LAKEHOUSE_ID}/Tables"

    con = duckdb.connect(str(DB_PATH), read_only=True)
    for name, query in _select_clauses().items():
        df = con.execute(query).fetch_arrow_table()
        write_deltalake(
            f"{base}/{name}",
            df,
            mode="overwrite",
            storage_options=storage_options,
        )
        print(f"  {name}: {df.num_rows:,} rows -> {base}/{name}")


if __name__ == "__main__":
    main()
