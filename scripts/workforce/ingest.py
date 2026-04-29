#!/usr/bin/env python3
"""
Phase 1 static-pack ingest — one-shot loader from `workforce/raw/`
into DuckDB at `workforce/state/wf.duckdb`.

Idempotent: drops + recreates each table on every run. Phase 1 is
static; no incremental updates. Phase 2 (live SF refresh, separate
session) introduces the streaming refresh path.

Per the AP/RW Phase 1 plan: docs/plans/2026-04-29-ap-rw-phase1-plan.md
"""

from __future__ import annotations

import pathlib
import sys

import duckdb

# Anchor paths to this file's location so ingest works from any cwd.
THIS_DIR = pathlib.Path(__file__).resolve().parent
REPO_ROOT = THIS_DIR.parent.parent
RAW_DIR = REPO_ROOT / "workforce" / "raw"
STATE_DIR = REPO_ROOT / "workforce" / "state"
DB_PATH = STATE_DIR / "wf.duckdb"
XLSX_PATH = RAW_DIR / "SalesOps_Workforce_Intelligence_v2.xlsx"
CSV_UNIFIED = RAW_DIR / "fact_activity_unified_all_dedup.csv.gz"
CSV_SALESOPS = RAW_DIR / "fact_activity_salesops_dedup_adj.csv.gz"

# Data sheets to ingest (skip README_Definitions + Charts — non-data).
XLSX_SHEETS = [
    "dim_people",
    "dim_leave",
    "dim_process",
    "dim_sales_hierarchy",
    "fact_activity_clean",
    "weekly_team_kpis",
    "weekly_person_kpis",
    "weekly_process_kpis",
    "forecast_output",
    "forecast_backtest_metrics",
    "coverage_matrix",
    "coverage_concentration",
    "anomalies_log",
]


def _ingest(con: duckdb.DuckDBPyConnection) -> dict[str, int]:
    """Drop+recreate all tables. Returns {table: row_count}."""
    counts: dict[str, int] = {}

    # Each xlsx sheet -> a DuckDB table of the same name. Use all_varchar
    # to defeat DuckDB's column-type sniffer — it guesses DOUBLE for
    # columns that contain Salesforce IDs (15- or 18-char alphanumeric)
    # and chokes on the first non-numeric value. Queries cast at use.
    for sheet in XLSX_SHEETS:
        con.execute(f"DROP TABLE IF EXISTS {sheet}")
        con.execute(
            f"""
            CREATE TABLE {sheet} AS
            SELECT * FROM read_xlsx(
                '{XLSX_PATH}', sheet='{sheet}', header=true, all_varchar=true
            )
            """
        )
        n = con.execute(f"SELECT COUNT(*) FROM {sheet}").fetchone()[0]
        counts[sheet] = n
        print(f"  {sheet:35s} {n:>6d} rows")

    # Two CSV.gz facts. read_csv_auto handles gzip transparently.
    for table, path in [
        ("fact_activity_unified", CSV_UNIFIED),
        ("fact_activity_salesops", CSV_SALESOPS),
    ]:
        con.execute(f"DROP TABLE IF EXISTS {table}")
        con.execute(
            f"""
            CREATE TABLE {table} AS
            SELECT * FROM read_csv_auto('{path}', compression='gzip')
            """
        )
        n = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        counts[table] = n
        print(f"  {table:35s} {n:>6d} rows")

    return counts


def main() -> int:
    if not XLSX_PATH.exists():
        print(f"FATAL: missing {XLSX_PATH}", file=sys.stderr)
        print(
            f"Run: unzip -o ~/Downloads/SalesOps_Workforce_Intelligence_v2_artifacts.zip "
            f"-d {RAW_DIR}/",
            file=sys.stderr,
        )
        return 1

    STATE_DIR.mkdir(parents=True, exist_ok=True)
    print(f"[1/2] Connecting to {DB_PATH}")
    con = duckdb.connect(str(DB_PATH))

    print(f"\n[2/2] Ingesting {len(XLSX_SHEETS)} xlsx sheets + 2 CSVs")
    counts = _ingest(con)

    # Sanity: total row count should be in the hundreds of thousands
    # (43k clean fact + 3k person-week + smaller sheets + 2 large CSVs).
    total = sum(counts.values())
    print(f"\n[OK] Ingested {len(counts)} tables, {total:,} total rows")
    print(f"     DuckDB at {DB_PATH}")
    print(f"     Verify: duckdb {DB_PATH} -c '.tables'")
    con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
