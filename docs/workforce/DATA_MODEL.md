# Workforce — Data Model (Phase 1 static pack)

DuckDB at `workforce/state/wf.duckdb`. 15 tables loaded from
`workforce/raw/SalesOps_Workforce_Intelligence_v2.xlsx` (13 sheets) +
2 fact CSVs. Source-of-truth contract: `workforce/raw/README_Workforce_Intelligence_v2.txt`.

All columns ingested as `VARCHAR` (DuckDB `all_varchar=true`) to defeat
the type-sniffer, which mis-guesses Salesforce IDs as DOUBLE. Queries
cast at use-site via `TRY_CAST(col AS BIGINT)` etc.

## Tables

### Dimension tables

| Table                 | Rows | Key columns                                                                                              |
| --------------------- | ---: | -------------------------------------------------------------------------------------------------------- |
| `dim_people`          |  762 | `person_id`, `canonical_name`, `role`                                                                    |
| `dim_leave`           |    1 | `person_id`, `leave_start`, `leave_end`, `leave_type`, `notes` (Andre's paternity 2025-04-14→2025-09-14) |
| `dim_process`         |    4 | `process_family`, `effort_weight`, `sla_target_days`, `notes`                                            |
| `dim_sales_hierarchy` |    0 | (empty in this snapshot — README says hierarchy not present in exports)                                  |

### Fact tables

| Table                    |    Rows | Notes                                                                                       |
| ------------------------ | ------: | ------------------------------------------------------------------------------------------- |
| `fact_activity_clean`    |  43,126 | 17 cols. Cleaned + deduped. Joinable to `dim_people` via `actor_name_raw = canonical_name`. |
| `fact_activity_unified`  | 271,424 | Full all-actors fact. Includes non-sales actors.                                            |
| `fact_activity_salesops` |  43,126 | Sales-Ops-only filtered + adjusted fact. Same row count as `fact_activity_clean`.           |

### Pre-rolled KPI tables

| Table                       |  Rows | Notes                                                                                                                                                            |
| --------------------------- | ----: | ---------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `weekly_team_kpis`          |   400 | 9 cols. Per-week × process_family team rollup.                                                                                                                   |
| `weekly_person_kpis`        | 3,100 | 16 cols. The MAIN scorecard table — per-person × week incl. `effort_units`, `actions`, `availability_factor`, `utilization_index_p75`, `utilization_p75_4w_avg`. |
| `weekly_process_kpis`       |   465 | 4 cols: `week_start`, `process_family`, `effort`, `actions`.                                                                                                     |
| `forecast_output`           |    48 | Forward-looking team capacity model: `week_start`, `p10`, `p50`, `p90`, `process_family`.                                                                        |
| `forecast_backtest_metrics` |     2 | MAE, MAPE, RMSE, Bias, P10_P90_Coverage. Per `process_family`.                                                                                                   |
| `coverage_matrix`           |    18 | Person × process_family effort breakdown.                                                                                                                        |
| `coverage_concentration`    |     6 | Per `segment × process_family` Herfindahl-style: `total_effort`, `effective_contributors`, `top1_share`, `top1_person_name`.                                     |
| `anomalies_log`             |     5 | Z-scored deviations from 8-week rolling avg.                                                                                                                     |

## Key columns (cross-table)

- **`event_week_start`** — Excel-serial date string (e.g. `46006` = Dec 2025). To convert: `DATE '1899-12-30' + INTERVAL (CAST(event_week_start AS INTEGER)) DAY`.
- **`actor_name_raw`** (in fact tables) ↔ **`canonical_name`** (in `dim_people`) — the join key.
- **`effort_units`** — weighted-event count: Opps=1, Quotes=2, KYC=3, Activities=0.5. Per `_effort.py`.
- **`utilization_index_p75`** — actions/avail-week normalized to the org's 75th percentile. `>1.0` = above-team-norm, `<0.5` = under.

## Effort weights

Live in `scripts/workforce/_effort.py`. Override per-family via env var:

```bash
export WORKFORCE_EFFORT_OPPORTUNITIES=1.5
export WORKFORCE_EFFORT_QUOTES_AND_PROPOSALS=2.5
```

## Re-ingest

`workforce/state/wf.duckdb` is local-only and gitignored. Re-create from raw:

```bash
unzip -o ~/Downloads/SalesOps_Workforce_Intelligence_v2_artifacts.zip -d workforce/raw/
python3 scripts/workforce/ingest.py
python3 -m pytest scripts/workforce/tests/ -v
```

Sentinel tests (5) are the correctness gate — Andre's paternity leave is the anchor.
