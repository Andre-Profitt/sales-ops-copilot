# RW VP Ops Scorecard — Power BI build (browser)

The semantic model is live with **25 DAX measures** covering **16 of 31** Richard Wyeth target KPIs. This doc is the curated browser-side build spec — drag-and-drop in Power BI Service.

## Where to start

https://app.fabric.microsoft.com/groups/b66233d5-9d4a-44ba-89a8-b70206d98ae7/datasets/3c58b5dd-b321-4aaa-a5cd-fb73e474edbb

Click the model → **Create report** (top right) → blank canvas.

## ⚠️ FIRST — set the page-level filter to current FY

The semantic model contains **3 fiscal years** of data (2024 + 2025 + 2026-YTD) so YoY math works. Without a page filter, headline tiles will show 3-year sums.

**Step before drag-and-drop:**

1. Right pane → Filters → "Filters on this page"
2. Drag `d_calendar[year]` → set value to `2026`
3. (Optional) Lock the filter so consumers can't unset it: filter pane → ... menu → "Lock filter"

This makes the dashboard open with current-year context. Trend visuals can still show 3-year history because they explicitly include `d_calendar[year]` on an axis (overrides page filter).

## Tables in the field list

```
f_opportunity        (8,278 rows × 24 cols)   — fact, ARR/ACV converted to org currency
f_stage_transition   (6,713 rows × 11 cols)   — fact, stage moves with days_in_prior_stage
d_account            (1,168)                   — region, country, industry
d_user               (218)                     — owner identity, role, title
d_region             (7)                       — slicer source, sorted NE→MEA
d_calendar           (1,491 days)              — date hierarchy
```

## DAX measures (25 total) by KPI mapping

### Headlines — drag onto KPI cards

| Measure                   | RW KPI                            | Target            |
| ------------------------- | --------------------------------- | ----------------- |
| `Total Closed Won ARR`    | forecast_closed_won               | Baseline +10% YoY |
| `Total Open Pipeline ARR` | pipeline_coverage_3x (numerator)  | 3x quota          |
| `Win Rate ARR`            | opp_win_rate (ARR-weighted)       | >25%              |
| `Win Rate Count`          | opp_win_rate (count-based)        | >25%              |
| `Avg Deal Size Won`       | closed_won_avg_deal_size          | >$500K            |
| `Avg Sales Cycle Days`    | sales_cycle_length                | <90d              |
| `Avg Open Opp Age Days`   | opp_age                           | <120d             |
| `Forecast Accuracy`       | (Phase 3 — needs ForecastingItem) | ±5%               |

### Stage hygiene — drag onto matrix or bar

| Measure                   | RW KPI                             | Target              |
| ------------------------- | ---------------------------------- | ------------------- |
| `Avg Days In Prior Stage` | time_in_stage                      | Baseline & optimize |
| `Stage Forward Pct`       | stage_conversion (proxy)           | >70%                |
| `Stage Backward Pct`      | (insight metric — flag regression) | track               |
| `Total Stage Transitions` | helper                             | —                   |

### Renewals — drag with motion=Renewal context

| Measure                  | RW KPI                 | Target       |
| ------------------------ | ---------------------- | ------------ |
| `Total Renewal ACV Won`  | renewals_mom_trend     | track        |
| `Total Renewal ACV Lost` | lost_arr_quarterly     | <5% annually |
| `Renewal Retention Pct`  | renewal_retention_rate | 95%          |

### Mix / source / pacing

| Measure                | RW KPI                                             | Target           |
| ---------------------- | -------------------------------------------------- | ---------------- |
| `Partner ARR`          | partner_opps_pct (numerator)                       | 20% of pipeline  |
| `Partner Pct`          | partner_opps_pct                                   | 20% of pipeline  |
| `Stage 3 Plus ARR`     | stage3_acv_value (proxy)                           | track            |
| `Source ARR Won`       | opp_source_effectiveness — slice by `lead_source`  | track            |
| `Source Win Rate`      | opp_source_effectiveness — slice by `lead_source`  | track            |
| `Total Land Won ARR`   | new_customer_reporting — slice by `region` × month | track            |
| `Total Land Won Count` | new_customer_reporting — slice by `region` × month | track            |
| `New Opps Created`     | new_opps_by_region                                 | 100/month/region |

### YoY comparison (use WITH the current-FY page filter set)

| Measure                  | Pairs with                          | Target                                     |
| ------------------------ | ----------------------------------- | ------------------------------------------ |
| `Closed Won ARR LY`      | `Total Closed Won ARR`              | —                                          |
| `Closed Won ARR YoY Pct` | standalone tile                     | **+10% YoY** (RW KPI: forecast_closed_won) |
| `Renewal ACV Won LY`     | `Total Renewal ACV Won`             | —                                          |
| `Renewal ACV YoY Pct`    | standalone tile                     | track                                      |
| `Pipeline ARR LY`        | `Total Open Pipeline ARR`           | —                                          |
| `Pipeline ARR YoY Pct`   | standalone tile (leading indicator) | track                                      |

YoY tiles read like this when you stack the 3 measures on one card visual:

```
┌──────────────────────────┐
│  Closed Won ARR (FY26)   │
│  $XX,XXX,XXX             │
│  vs $XX,XXX,XXX (FY25)   │
│  +X.X% YoY  ← target +10%│
└──────────────────────────┘
```

### Helpers (denominators)

| Measure                      | Use                                |
| ---------------------------- | ---------------------------------- |
| `Total Closed Lost ARR`      | denominator for Win Rate ARR       |
| `Open Opp Count`             | scaling for pipeline checks        |
| `Forward Stage Transitions`  | denominator for Stage Forward Pct  |
| `Backward Stage Transitions` | denominator for Stage Backward Pct |

## Recommended layout (8 visuals, single page)

Layout assumes 1280×720 canvas, page-size "16:9". Adjust as needed.

```
┌─────────────── Page 1: VP Ops Scorecard ───────────────────────────┐
│ ┌──────────────────┐  ┌───────────────────┐  ┌──────────────────┐ │
│ │ Slicer           │  │ Slicer            │  │ Slicer           │ │
│ │ d_region[region] │  │ d_calendar[fiscal_│  │ f_opp[motion_    │ │
│ │                  │  │  quarter]          │  │  type]           │ │
│ └──────────────────┘  └───────────────────┘  └──────────────────┘ │
│                                                                     │
│ ┌────────┬────────┬────────┬────────┬────────┐                    │
│ │ Won ARR│Pipe ARR│Win Rate│Avg Cyc │Open Age│  ← KPI cards       │
│ └────────┴────────┴────────┴────────┴────────┘                    │
│                                                                     │
│ ┌──────────────────────────────┐  ┌────────────────────────────┐  │
│ │ 1. Won ARR by region × FQ    │  │ 2. Stage hygiene           │  │
│ │    matrix, conditional fmt   │  │    rows = from_stage_name  │  │
│ │                               │  │    cols = Forward/Backward│  │
│ │                               │  │    Pct, days_in_prior     │  │
│ └──────────────────────────────┘  └────────────────────────────┘  │
│                                                                     │
│ ┌──────────────────────────────┐  ┌────────────────────────────┐  │
│ │ 3. Renewal Retention by      │  │ 4. Lead source funnel      │  │
│ │    region (line, target line │  │    Source ARR Won + Source │  │
│ │    at 95%)                    │  │    Win Rate by lead_source │  │
│ └──────────────────────────────┘  └────────────────────────────┘  │
│                                                                     │
│ ┌──────────────────────────────────────────────────────────────┐  │
│ │ 5. New Land deals by region × month                           │  │
│ │    matrix, region rows, year_month cols, Total Land Won ARR  │  │
│ └──────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
```

## Conditional formatting against targets (do per visual)

For each KPI tile, set conditional formatting against the target:

- `Win Rate ARR` < 0.25 → red, ≥ 0.25 → green
- `Avg Sales Cycle Days` > 90 → red, ≤ 90 → green
- `Avg Open Opp Age Days` > 120 → red, ≤ 120 → green
- `Renewal Retention Pct` < 0.95 → red, ≥ 0.95 → green
- `Stage Forward Pct` < 0.70 → amber, ≥ 0.70 → green
- `Partner Pct` < 0.20 → amber, ≥ 0.20 → green

## Compliance text box (paste on page 1, footer)

> **Methodology + caveats.** ARR (Land+Expand) and ACV (Renewal) are tracked separately per SimCorp commercial rules — never blended. All values FX-converted to org currency at row level via SOQL `convertCurrency()`. Phase 3 KPIs not yet in model: forecast accuracy (ForecastingItem snapshots), commercial-approval timing (ApprovalProcess), existing ARR run-rate + indexation (Asset/Subscription), synergy / cross-sell-to-acquired (custom Account/Opp fields), product-mix (OpportunityLineItem). Source: `scripts/sales/rw_kpi_graph.py` schema v1.

## Save + share

- Save report as `rpt_vp_ops_scorecard`
- App workspace: `Salesforce Analytics - Sales Manager`
- Share with Richard Wyeth (`richard.wyeth@simcorp.com`) as Viewer
- Set as featured for the workspace if appropriate

## Refresh model

Run nightly via launchd (Phase 3 hardening):

```bash
python3 scripts/sales/sf_to_fabric_rw.py            # opp/account/user
python3 scripts/sales/sf_to_fabric_rw_phase2.py     # OFH stage transitions
# semantic model uses Direct Lake — auto-picks up new data on next query
```
