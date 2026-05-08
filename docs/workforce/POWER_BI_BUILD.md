# RW Workforce — Power BI build

## What's already done (CLI, from Mac)

- Lakehouse `lkh_workforce_rw` created in workspace **Salesforce Analytics - Sales Manager**
  - Workspace ID: `b66233d5-9d4a-44ba-89a8-b70206d98ae7`
  - Lakehouse ID: `34ea3a8c-6493-45ab-ab28-1d14bed9987f`
- 6 delta tables written from `wf.duckdb` with proper typing (Excel-serial dates → DATE, all metrics → DOUBLE):

| Table                    | Rows  | Grain                                                       |
| ------------------------ | ----- | ----------------------------------------------------------- |
| `weekly_person_kpis`     | 3,100 | person × week (20 distinct people, 2023-01-02 → 2025-12-15) |
| `weekly_team_kpis`       | 400   | team × week                                                 |
| `coverage_concentration` | 6     | segment × process_family                                    |
| `dim_people`             | 762   | roster (inferred — see KG constraint `roster_inferred`)     |
| `anomalies_log`          | 5     | logged z-score anomalies                                    |
| `forecast_output`        | 48    | 48-week forward capacity, by process_family                 |

Repush script: `scripts/workforce/wf_push_to_fabric.py` — re-run nightly after wf.duckdb refresh (Phase 2).

## Ship the report

The semantic model + report are pushed via Fabric REST — no browser drag-and-drop. Three scripts, in order:

```bash
python3 scripts/workforce/wf_push_to_fabric.py        # 6 delta tables → lkh_workforce_rw
python3 scripts/workforce/wf_push_semantic_model.py   # sm_workforce_rw (12 measures)
python3 scripts/workforce/wf_push_report.py           # rpt_workforce_rw (12 visualContainers)
```

All three are idempotent — re-running updates definition in place.

**Live state (verified 2026-05-08):**

| Asset                            | id                                     |
| -------------------------------- | -------------------------------------- |
| Workspace                        | `b66233d5-9d4a-44ba-89a8-b70206d98ae7` |
| Lakehouse `lkh_workforce_rw`     | `34ea3a8c-6493-45ab-ab28-1d14bed9987f` |
| Semantic model `sm_workforce_rw` | `3ddb779b-...`                         |
| Report `rpt_workforce_rw`        | `c5d3e72a-1140-4c6d-aa3e-15a5a485782e` |

Open report: https://app.fabric.microsoft.com/groups/b66233d5-9d4a-44ba-89a8-b70206d98ae7/reports/c5d3e72a-1140-4c6d-aa3e-15a5a485782e

## Visual contract (what `wf_push_report.py` ships)

12 visualContainers on a single page. Layout is set by the script; tweak in browser if desired.

| #   | Visual              | Fields                                                                                                                                                                           |
| --- | ------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 0   | Slicer              | `weekly_person_kpis.event_week_start`                                                                                                                                            |
| 1   | Slicer              | `weekly_person_kpis.canonical_name`                                                                                                                                              |
| 2–5 | KPI cards (row)     | `Total Effort`, `Avg Util P75 By Person`, `Overloaded Persons`, `Underloaded Persons`                                                                                            |
| 6   | Heatmap (matrix)    | rows=`canonical_name`, cols=`event_week_start`, values=`Mean Util P75`, conditional fmt: red >1.5, blue <0.5, grey 0.5–1.5 (thresholds mirrored from `wf_kpi_graph._THRESHOLDS`) |
| 7   | Line chart          | x=`event_week_start`, y=`Mean Util P75 4w`, series=`canonical_name`                                                                                                              |
| 8   | Stacked bar         | x=`canonical_name`, y=`Total Effort`, series=`process_family` from `coverage_concentration` (proxy — see "Known limitations" below)                                              |
| 9   | Scatter             | x=`Mean Availability`, y=`Total Effort Adj`, dot=`canonical_name`                                                                                                                |
| 10  | Concentration table | from `coverage_concentration`: `segment`, `process_family`, `top1_person_name`, `top1_share`, with cell highlight when `top1_share > 0.5`                                        |
| 11  | Compliance text-box | verbatim AI Code §8 wording (see "Compliance" section below)                                                                                                                     |

## Known limitations

- **Stacked bar (#8) renders a single uncategorized series** until a `weekly_person_kpis` ↔ `coverage_concentration` relationship exists in the model. `weekly_person_kpis` has no `process_family` column, so the series binding is a cross-table fallback. Real fix is upstream: add a `process_family` rollup at the person × week grain in `wf_push_semantic_model.py` (or upstream of `wf.duckdb` in `scripts/workforce/ingest.py`). Not blocking — the rest of the report works.

## Editing the report

If you tweak via browser and want changes persisted, re-run `wf_push_report.py` with your changes mirrored in code. **Do NOT** save browser changes as the canonical state — the script will overwrite on next deploy.

## DAX measures (12 published in `sm_workforce_rw`)

Source of truth: `scripts/workforce/wf_push_semantic_model.py`. Re-run that script to update measure definitions; do **not** edit measures in browser as the canonical state.

| Measure                   | Binds to                                                       | Used by visual           |
| ------------------------- | -------------------------------------------------------------- | ------------------------ |
| `Total Actions`           | `SUM(weekly_person_kpis[actions])`                             | (helper)                 |
| `Total Actions Adj`       | `SUM(weekly_person_kpis[actions_adj])`                         | (helper)                 |
| `Total Effort`            | `SUM(weekly_person_kpis[effort_units])`                        | KPI card #2, stacked bar |
| `Total Effort Adj`        | `SUM(weekly_person_kpis[effort_adj])`                          | scatter (y)              |
| `Mean Availability`       | `AVERAGE(weekly_person_kpis[availability_factor])`             | scatter (x)              |
| `Mean Util P75`           | `AVERAGE(weekly_person_kpis[utilization_index_p75])`           | heatmap values           |
| `Avg Util P75 By Person`  | `AVERAGEX` over distinct `person_id` of `Mean Util P75`        | KPI card #3              |
| `Mean Util P75 4w`        | `AVERAGE(weekly_person_kpis[utilization_p75_4w_avg])`          | line chart (y)           |
| `Overloaded Persons`      | `DISTINCTCOUNT(person_id)` where `utilization_index_p75 > 1.5` | KPI card #4              |
| `Underloaded Persons`     | `DISTINCTCOUNT(person_id)` where `utilization_index_p75 < 0.5` | KPI card #5              |
| `Overloaded Person-Weeks` | `COUNTROWS` where `utilization_index_p75 > 1.5`                | (helper)                 |
| `Point SPOF Count`        | `COUNTROWS(coverage_concentration)` where `top1_share > 0.5`   | (helper)                 |

Thresholds (`>1.5`, `<0.5`, `>0.5`) are mirrored verbatim from `wf_kpi_graph._THRESHOLDS` — single source of truth for both the measure definitions and the heatmap conditional formatting.

## Compliance text box (rendered on page 1 by `wf_push_report.py`)

The text-box is shipped automatically by `wf_push_report.py` (visualContainer #11). Source string lives in the script's `COMPLIANCE_TEXT` constant — verbatim:

> **Methodology and constraints.** Effort is a weighted-event proxy; no time-tracking exists. Roster is inferred (replace with authoritative source when available). Per AI Code of Conduct §8: do **not** use these KPIs for per-individual evaluative or predictive judgments. Forecast is at process-family granularity only. Static-pack data ends 2025-12-15. Source: `scripts/workforce/wf_kpi_graph.py` (schema v1).

## Refresh model

Phase 1 (now): static pack, ends 2025-12-15. Republish only when the source `wf.duckdb` changes — re-run `wf_push_to_fabric.py`. The semantic model uses Direct Lake against the lakehouse, so it picks up new lakehouse data on next query without a model republish. The report definition (`wf_push_report.py`) only needs re-running when the visual contract changes, not on data refresh.

Phase 2: live SF refresh of wf.duckdb (separate work item). Add a launchd schedule that runs `ingest.py` then `wf_push_to_fabric.py`.
