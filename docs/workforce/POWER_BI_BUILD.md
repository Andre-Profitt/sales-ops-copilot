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

## Browser steps in Power BI Service (~1 hour)

### 1. Open the Lakehouse

Browser → https://app.fabric.microsoft.com → workspace **Salesforce Analytics - Sales Manager** → `lkh_workforce_rw`

You should see 6 tables under the Tables tree. If they aren't visible, click the refresh icon (SQL endpoint provisioning takes a few minutes after first write).

### 2. Create the semantic model

Top right → **New semantic model** → name `sm_workforce_rw` → tick all 6 tables → Confirm.

Open `sm_workforce_rw` → **Open data model** to set relationships:

- `weekly_person_kpis[person_id]` → `dim_people[person_id]` (many-to-one)
- `weekly_person_kpis[event_week_start]` should be marked as date dimension

### 3. Paste the DAX measures

Right-click `weekly_person_kpis` → New measure → paste each block from the next section. The thresholds match `wf_kpi_graph.GRAPH.thresholds` verbatim — single source of truth.

### 4. Build the report

From the semantic model → **Create report**. 6 visuals, in this order:

| #   | Visual              | Fields                                                                                                                                    |
| --- | ------------------- | ----------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | KPI cards (row)     | `Total Effort`, `Avg Util P75`, `Overloaded Count`, `Underloaded Count`                                                                   |
| 2   | Heatmap (matrix)    | rows=`canonical_name`, cols=`event_week_start`, values=`Util Index P75`, conditional fmt: red >1.5, grey 0.5–1.5, blue <0.5               |
| 3   | Line chart          | x=`event_week_start`, y=`Util P75 4w Avg`, series=`canonical_name` (filter to top 10 by activity)                                         |
| 4   | Stacked bar         | x=`canonical_name`, y=`Effort Units`, series=`process_family` (need join via fact_activity if needed)                                     |
| 5   | Scatter             | x=`Availability Factor`, y=`Effort Adj`, dot=`canonical_name`                                                                             |
| 6   | Concentration table | from `coverage_concentration`: `segment`, `process_family`, `top1_person_name`, `top1_share`, with cell highlight when `top1_share > 0.5` |

Add a slicer for `event_week_start` and a slicer for `canonical_name`. Save as `rpt_workforce_rw`.

### 5. Publish + share

The report is already in the workspace. Share via Power BI Service (don't email PBIX files).

## DAX measures (paste-ready)

```dax
Actions =
SUM ( weekly_person_kpis[actions] )

Actions Adj =
SUM ( weekly_person_kpis[actions_adj] )

Total Effort =
SUM ( weekly_person_kpis[effort_units] )

Effort Adj =
SUM ( weekly_person_kpis[effort_adj] )

Availability Factor =
AVERAGE ( weekly_person_kpis[availability_factor] )

Util Index P75 =
AVERAGE ( weekly_person_kpis[utilization_index_p75] )

Avg Util P75 =
AVERAGEX (
    VALUES ( weekly_person_kpis[person_id] ),
    [Util Index P75]
)

Util P75 4w Avg =
AVERAGE ( weekly_person_kpis[utilization_p75_4w_avg] )

Overloaded Count =
CALCULATE (
    DISTINCTCOUNT ( weekly_person_kpis[person_id] ),
    weekly_person_kpis[utilization_index_p75] > 1.5
)

Underloaded Count =
CALCULATE (
    DISTINCTCOUNT ( weekly_person_kpis[person_id] ),
    weekly_person_kpis[utilization_index_p75] < 0.5
)

Person-Weeks Overloaded =
CALCULATE (
    COUNTROWS ( weekly_person_kpis ),
    weekly_person_kpis[utilization_index_p75] > 1.5
)

SPOF Segment-Processes =
CALCULATE (
    COUNTROWS ( coverage_concentration ),
    coverage_concentration[top1_share] > 0.5
)
```

## Compliance — paste this as a text box on page 1 of the report

> **Methodology and constraints.** Effort is a weighted-event proxy; no time-tracking exists. Roster is inferred (replace with authoritative source when available). Per AI Code of Conduct §8: do **not** use these KPIs for per-individual evaluative or predictive judgments. Forecast is at process-family granularity only. Static-pack data ends 2025-12-15. Source: `scripts/workforce/wf_kpi_graph.py` (schema v1).

## Refresh model

Phase 1 (now): static pack, 2025-12-15. Republish only when the source `wf.duckdb` changes — re-run `wf_push_to_fabric.py`.

Phase 2: live SF refresh of wf.duckdb (separate work item). Add a launchd schedule that runs `ingest.py` then `wf_push_to_fabric.py`. Power BI semantic model picks up changes via Direct Lake on next query.
