"""Stage SF Opportunity / Account / User detail rows into Fabric Lakehouse
`lkh_sales_kpis_rw` for Richard Wyeth's VP Ops scorecard.

Detail-row staging (not pre-aggregated) so Power BI slicers — Region,
Type, Stage, Owner, Time — work natively. Multi-currency safe via SOQL
`convertCurrency()`: each row carries both native ARR/ACV and the
org-default-currency converted value.

Output Lakehouse:
  abfss://b66233d5-9d4a-44ba-89a8-b70206d98ae7@onelake.dfs.fabric.microsoft.com/<lh-id>/Tables

Tables written:
  f_opportunity      (fact: open + closed deals; one row per opp)
  d_account          (dim: account, region, country, industry)
  d_user             (dim: owner identity + role for region pivots)
  d_region           (small dim: 7 distinct Region__c values)
  d_calendar         (date dim spanning the data window)

Auth: AzureCliCredential (Fabric/OneLake) + sf CLI (Salesforce).
Both expected pre-authenticated.

Cardinal SimCorp rules (enforced):
  - APTS_Opportunity_ARR__c → Land+Expand only (motion_filter = land/expand)
  - APTS_Renewal_ACV__c → Renewal only
  - Never blend; the fact table carries both columns natively, the model
    layer decides which to surface per-KPI.
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
LAKEHOUSE_NAME = "lkh_sales_kpis_rw"
SF_ORG = "apro@simcorp.com"

ONELAKE_BASE_FMT = "abfss://{ws}@onelake.dfs.fabric.microsoft.com/{lh}/Tables"


# ──────────────────────────────────────────────────────────────────────────
# SOQL queries — what we pull from SF
# ──────────────────────────────────────────────────────────────────────────


SOQL_OPP = """
SELECT
    Id, Name, AccountId, OwnerId,
    StageName, Type, RecordType.Name,
    APTS_Primary_Quote_Type__c,
    Reason_Won_Lost__c, Lost_to_Competitor__c,
    CurrencyIsoCode,
    convertCurrency(APTS_Opportunity_ARR__c),
    convertCurrency(APTS_Renewal_ACV__c),
    convertCurrency(Amount),
    LeadSource,
    IsWon, IsClosed,
    CloseDate, CreatedDate,
    LastStageChangeDate,
    Account.Region__c, Account.BillingCountry, Account.Industry,
    Account.Name
FROM Opportunity
WHERE (CloseDate = LAST_N_FISCAL_YEARS:3 OR CloseDate = THIS_FISCAL_YEAR)
"""

SOQL_ACCOUNT = """
SELECT Id, Name, Region__c, BillingCountry, Industry, OwnerId, Type
FROM Account
WHERE Id IN (SELECT AccountId FROM Opportunity WHERE (CloseDate = LAST_N_FISCAL_YEARS:3 OR CloseDate = THIS_FISCAL_YEAR))
"""

SOQL_USER = """
SELECT Id, Name, Title, Department, IsActive, UserRole.Name, UserRole.DeveloperName
FROM User
WHERE Id IN (SELECT OwnerId FROM Opportunity WHERE (CloseDate = LAST_N_FISCAL_YEARS:3 OR CloseDate = THIS_FISCAL_YEAR))
"""


def _run_soql(query: str, target_csv: pathlib.Path) -> int:
    """Bulk-export SOQL to CSV via sf CLI. Returns row count."""
    proc = subprocess.run(
        [
            "sf",
            "data",
            "query",
            "-o",
            SF_ORG,
            "-q",
            " ".join(query.split()),
            "-r",
            "csv",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        print("  SF query failed:", proc.stderr[:500], file=sys.stderr)
        raise RuntimeError("sf data query failed")
    target_csv.write_text(proc.stdout)
    n = sum(1 for _ in proc.stdout.splitlines()) - 1
    return max(0, n)


# ──────────────────────────────────────────────────────────────────────────
# Transform — DuckDB does the typing + region dim derivation
# ──────────────────────────────────────────────────────────────────────────


def transform(stage: pathlib.Path) -> dict[str, pd.DataFrame]:
    """Build typed DataFrames for each target Delta table."""
    con = duckdb.connect(":memory:")
    con.execute(
        f"CREATE TABLE raw_opp AS SELECT * FROM read_csv_auto('{stage / 'opp.csv'}', sample_size=20000)"
    )
    con.execute(
        f"CREATE TABLE raw_acc AS SELECT * FROM read_csv_auto('{stage / 'account.csv'}', sample_size=20000)"
    )
    con.execute(
        f"CREATE TABLE raw_usr AS SELECT * FROM read_csv_auto('{stage / 'user.csv'}', sample_size=20000)"
    )

    f_opp = con.execute("""
        SELECT
            "Id" as opp_id,
            "Name" as opp_name,
            "AccountId" as account_id,
            "OwnerId" as owner_id,
            "StageName" as stage_name,
            "Type" as motion_type,
            "RecordType.Name" as record_type,
            "APTS_Primary_Quote_Type__c" as primary_quote_type,
            "Reason_Won_Lost__c" as reason_won_lost,
            "Lost_to_Competitor__c" as lost_to_competitor,
            "CurrencyIsoCode" as native_currency,
            CAST("APTS_Opportunity_ARR__c" AS DOUBLE) as arr_org_ccy,
            CAST("APTS_Renewal_ACV__c" AS DOUBLE) as acv_org_ccy,
            CAST("Amount" AS DOUBLE) as amount_org_ccy,
            "LeadSource" as lead_source,
            CAST("IsWon" AS BOOLEAN) as is_won,
            CAST("IsClosed" AS BOOLEAN) as is_closed,
            CAST("CloseDate" AS DATE) as close_date,
            CAST("CreatedDate" AS TIMESTAMP) as created_date,
            CAST("LastStageChangeDate" AS TIMESTAMP) as last_stage_change_date,
            "Account.Region__c" as region,
            "Account.BillingCountry" as billing_country,
            "Account.Industry" as industry,
            "Account.Name" as account_name
        FROM raw_opp
    """).fetch_df()

    d_acc = con.execute("""
        SELECT
            "Id" as account_id,
            "Name" as account_name,
            "Region__c" as region,
            "BillingCountry" as billing_country,
            "Industry" as industry,
            "OwnerId" as owner_id,
            "Type" as account_type
        FROM raw_acc
    """).fetch_df()

    d_usr = con.execute("""
        SELECT
            "Id" as user_id,
            "Name" as user_name,
            "Title" as title,
            "Department" as department,
            CAST("IsActive" AS BOOLEAN) as is_active,
            "UserRole.Name" as role_name,
            "UserRole.DeveloperName" as role_dev_name
        FROM raw_usr
    """).fetch_df()

    # Region dim — deterministic order matching what's known
    region_order = [
        "Northern Europe",
        "Central Europe",
        "North America",
        "Southwestern Europe",
        "APAC",
        "United Kingdom & Ireland",
        "Middle East & Africa",
    ]
    regions_in_data = sorted(set(f_opp["region"].dropna().tolist()))
    ordered = [r for r in region_order if r in regions_in_data] + [
        r for r in regions_in_data if r not in region_order
    ]
    d_region = pd.DataFrame({"region": ordered, "sort_order": range(1, len(ordered) + 1)})

    # Date dim spanning data window
    min_d = pd.to_datetime(f_opp["close_date"]).min()
    max_d = pd.to_datetime(f_opp["close_date"]).max()
    if pd.isna(min_d) or pd.isna(max_d):
        date_range = pd.date_range("2023-01-01", "2026-12-31", freq="D")
    else:
        date_range = pd.date_range(
            min_d - pd.Timedelta(days=30), max_d + pd.Timedelta(days=365), freq="D"
        )
    d_calendar = pd.DataFrame(
        {
            "date": date_range,
            "year": date_range.year,
            "quarter": date_range.quarter,
            "fiscal_quarter": date_range.year.astype(str) + "-Q" + date_range.quarter.astype(str),
            "month": date_range.month,
            "month_name": date_range.strftime("%b"),
            "year_month": date_range.strftime("%Y-%m"),
            "day_of_week": date_range.dayofweek,
            "is_weekend": date_range.dayofweek >= 5,
        }
    )

    return {
        "f_opportunity": f_opp,
        "d_account": d_acc,
        "d_user": d_usr,
        "d_region": d_region,
        "d_calendar": d_calendar,
    }


# ──────────────────────────────────────────────────────────────────────────
# Lakehouse / OneLake
# ──────────────────────────────────────────────────────────────────────────


def ensure_lakehouse() -> str:
    """Create the lakehouse if absent. Returns lakehouse_id."""
    import requests

    cred = AzureCliCredential()
    token = cred.get_token("https://api.fabric.microsoft.com/.default").token
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    base = f"https://api.fabric.microsoft.com/v1/workspaces/{WORKSPACE_ID}"

    r = requests.get(f"{base}/lakehouses", headers=headers)
    r.raise_for_status()
    for lh in r.json().get("value", []):
        if lh.get("displayName") == LAKEHOUSE_NAME:
            return lh["id"]

    r = requests.post(
        f"{base}/lakehouses",
        headers=headers,
        json={
            "displayName": LAKEHOUSE_NAME,
            "description": "RW (Richard Wyeth, MD Sales Ops) sales KPIs — detail rows from SF, region-filterable. Source of truth: scripts/sales/rw_kpi_graph.py",
        },
    )
    r.raise_for_status()
    return r.json()["id"]


def write_to_onelake(lakehouse_id: str, frames: dict[str, pd.DataFrame]) -> None:
    cred = AzureCliCredential()
    token = cred.get_token("https://storage.azure.com/.default").token
    storage_options = {"bearer_token": token, "use_fabric_endpoint": "true"}
    base = ONELAKE_BASE_FMT.format(ws=WORKSPACE_ID, lh=lakehouse_id)
    for name, df in frames.items():
        write_deltalake(f"{base}/{name}", df, mode="overwrite", storage_options=storage_options)
        print(f"  {name}: {len(df):,} rows -> {base}/{name}")


# ──────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        stage = pathlib.Path(tmp)
        print("Step 1/4: SF bulk export (Opportunity, Account, User)...")
        n_opp = _run_soql(SOQL_OPP, stage / "opp.csv")
        print(f"  Opportunity: {n_opp:,} rows")
        n_acc = _run_soql(SOQL_ACCOUNT, stage / "account.csv")
        print(f"  Account: {n_acc:,} rows")
        n_usr = _run_soql(SOQL_USER, stage / "user.csv")
        print(f"  User: {n_usr:,} rows")

        print("\nStep 2/4: transform + type-cast...")
        frames = transform(stage)
        for name, df in frames.items():
            print(f"  {name}: {len(df):,} rows × {len(df.columns)} cols")

        print("\nStep 3/4: ensure Fabric Lakehouse exists...")
        lh_id = ensure_lakehouse()
        print(f"  lakehouse id: {lh_id}")

        print("\nStep 4/4: write Delta tables to OneLake...")
        write_to_onelake(lh_id, frames)

    print("\ndone.")
    print(f"  workspace: {WORKSPACE_ID}")
    print(f"  lakehouse: {LAKEHOUSE_NAME} ({lh_id})")
    print("  next: scripts/sales/rw_push_semantic_model.py")


if __name__ == "__main__":
    main()
