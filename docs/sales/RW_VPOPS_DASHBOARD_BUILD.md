# RW VP Ops Scorecard — Power BI build (browser)

The semantic model is live with **55 DAX measures** covering **16 of 31** Richard Wyeth target KPIs (the rest are Phase 3 — they need ForecastingItem snapshots, ApprovalProcess history, Asset/Subscription, or custom Account/Opp fields not yet in the model). This doc is the curated browser-side build spec — drag-and-drop in Power BI Service.

The 16 covered KPIs are: `forecast_closed_won`, `pipeline_coverage_3x`, `opp_win_rate`, `closed_won_avg_deal_size`, `sales_cycle_length`, `opp_age`, `stage3_acv_value`, `partner_opps_pct`, `renewals_mom_trend`, `lost_arr_quarterly`, `renewal_retention_rate`, `new_opps_by_region`, `opp_source_effectiveness`, `new_customer_reporting`, `time_in_stage`, `stage_conversion`. Source of truth for KPI definitions, targets, motion filters, and caveats: `scripts/sales/rw_kpi_graph.py`.

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

## DAX measures (55 total) by KPI mapping

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
| `Stage Forward Pct`       | stage_conversion (all motions)     | >70%                |
| `Stage Forward Pct (LE)`  | stage_conversion (Land+Expand)     | >70%                |
| `Stage Backward Pct`      | (insight metric — flag regression) | track               |
| `Total Stage Transitions` | helper                             | —                   |

**Per-stage forward rates (Land+Expand only — `motion_filter='land_expand'` per KG)** — drag for stage-by-stage funnel hygiene. Stage 3→4 and Stage 4→5 carry the funnel-skip caveat from `rw_kpi_graph.py`: ~70% of close-wons skip Stage 4 in OFH, so those two measures are over a partial population. Surface that caveat as a footer note on those visuals.

| Measure               | Transition                  | Target                     |
| --------------------- | --------------------------- | -------------------------- |
| `Stage 1 Forward Pct` | Prospecting → Discovery     | >70%                       |
| `Stage 2 Forward Pct` | Discovery → Engagement      | >70%                       |
| `Stage 3 Forward Pct` | Engagement → Decision-Maker | >70% (caveat: funnel-skip) |
| `Stage 4 Forward Pct` | Decision-Maker → Preferred  | >70% (caveat: funnel-skip) |
| `Stage 5 Forward Pct` | Preferred → Contracting     | >70%                       |
| `Stage 6 Forward Pct` | Contracting → Won           | >70%                       |

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

## 2026-05-08 — Foundation Phase Complete

Foundation for the 5-tab redesign (spec: `docs/superpowers/specs/2026-05-08-rw-dashboard-redesign-design.md`, plan: `docs/superpowers/plans/2026-05-08-rw-dashboard-foundation.md`).

### Builders shipped (`scripts/sales/_pbir_helpers.py`)

- `build_card_visual` — extracted from `rw_add_visual.py`
- `build_slicer_visual` — extracted
- `build_table_visual` — `tableEx` with mixed column / measure projections
- `build_matrix_visual` — `pivotTable` with rows / columns / values axes
- `add_page` / `remove_page` / `ensure_pages` — idempotent page management

All five live-probed against `rpt_vp_ops_scorecard` Fabric LRO and accepted.

### Pages live in `rpt_vp_ops_scorecard`

`VP Ops Scorecard` (original 26 visuals + leftover probe table + matrix from Tasks 3-4 — `--clear` to wipe) plus the 5 redesign tabs:

- PageWhatChanged (`What Changed`)
- PageForecast (`Forecast`)
- PageStageHygiene (`Stage Hygiene`)
- PageRenewals (`Renewals`)
- PageGrowthMix (`Growth Mix`)

All five new tabs are empty — ready for per-tab visual composition.

### DAX measures shipped

98 total measures in `sm_sales_kpis_rw` (verify via `python3 -m scripts.sales.rw_inventory_measures`). Net new this session:

| Family | Count | Source |
|---|---|---|
| Stage Backward Pct (LE) + 6 per-stage | 7 | f_stage_transition |
| Avg Days In Prior Stage (LE) + 6 per-stage | 7 | f_stage_transition |
| Stalled Open Opps Count/ARR × {14d, 21d} | 4 | f_opportunity |
| At Risk / Watch / Healthy × {Count, ARR} | 6 | f_opportunity (+ rel) |
| Window deltas: New/Won/Lost × {1d, 7d, FQTD} | 9 | f_opportunity |
| Window deltas: Stage Moves Count/ARR + Backward Moves × {1d, 7d, FQTD} | 9 | f_stage_transition |
| S3+ Open ACV | 1 | f_opportunity |

### Schema deltas vs. plan draft

The plan draft was authored against assumed columns; real schema reality-check (verified vs deployed model + SF metadata):

- `f_stage_transition[direction]` is `"forward"`/`"backward"` (string), not `1`/`-1` (int)
- `f_stage_transition[transition_at]` (not `transition_date`)
- `f_stage_transition[days_in_prior_stage]` (not `days_in_from_stage`)
- `f_opportunity` has no `stage_num` column → stage filters use `stage_name IN {...}` with verified OpportunityStage names
- Last-stage-move date already lives on `f_opportunity[last_stage_change_date]` → no LOOKUP through f_stage_transition needed for stall detection
- Existing `Stage Backward Pct` already in model → only per-stage variants are net-new

All new measures above use the real schema and were live-deployed (Fabric LRO succeeded for each commit).

### Deferred to follow-up plans

Requires SF SOQL pull additions in `sf_to_fabric_rw.py` + ETL run before measures can ship:

- **S3+ Approval Compliance Pct** — needs `Stage_20_Approval__c` (label "Commercial Approval") added to f_opportunity
- **Slips family** (3 window-delta measures) — needs `f_ofh_close_date` table (CloseDate OFH pull)
- **Growth Mix family** (Task 12, ~6 measures: SaaS YoY, Synergy pipe/won) — `Synergy` field doesn't exist on Opportunity; SaaS measures need `APTS_RH_ASP_Annual__c` ("SimCorp SaaS ACV") added to ETL pull
- ILF/ALF pipeline split, cross-sell-to-acquired, PS attach, one-off revenue — need new ETL extensions
- **Per-tab visual composition** — 5 separate per-tab planning sessions using the primitives + measures shipped here

### Tests

`tests/sales/test_pbir_helpers.py` — 8 passing tests covering all helper builders and page-management primitives.

## 2026-05-08 — Tab 1 (What Changed) shipped

Composed via `scripts/sales/rw_compose_what_changed.py`. Idempotent — re-run wipes and rebuilds.

**Visuals shipped (12):**

- Risk band: At Risk · Watch · Healthy × {count, ARR} = 6 cards
- Change buckets: Stage Moves (count + ARR) · New Opps · Won · Lost = 5 cards
- Detail table: Top open opps by Open ARR (6 columns) = 1 table

**Spec deviations (path-(a) deferrals):**

- Slips card: needs `f_ofh_close_date` ETL (deferred per foundation)
- Detail table "Change" + "Risk class" columns: row-context measures TBD
- Detail table top-20 filter: apply via PBI Visual filter pane manually until `build_table_visual` grows a `top_n` kwarg
- Window slicer: field-parameter shape not in `_pbir_shapes.py`; cards use the 7d window today
- Conditional formatting on Risk band: `objects` shape not yet captured (use `rw_capture_visual.py` after browser-authoring one)

**Pre-flight:** the composer runs every visual through `validate_visual_dict` against the deployed `sm_sales_kpis_rw` before pushing. Catches measure-name typos pre-LRO.

**To rebuild:** `python3 -m scripts.sales.rw_compose_what_changed`

## 2026-05-08 — Tab 2 (Forecast) shipped

Composed via `scripts/sales/rw_compose_forecast.py`. Idempotent. Model now at 100 measures (added: `Days Remaining In FQ`, `Total Open Pipeline Value`).

**Visuals shipped (9):**

- Hero (3 cards): Days Remaining (FQ) · Open Pipeline Value (cross-motion) · Closed Won ARR
- Stage × Motion matrix (rows=stage_name, cols=motion_type, value=Open Value)
- Forecast discipline (4 cards): Slip Rate · Total Slips · Total Upgrades · Avg Days In Category
- Commit-risk table (6 cols): Opp · Account · Stage · Value · Close Date · Last Stage Move

**Spec deviations (path-(a) deferrals):**

- Quota attainment + Pipeline coverage 3x cards: need `Quota__c` per region
- Stage × motion "Weighted" column: no win-prob-by-stage in model; ship Open Value only
- Region split table: needs quota
- Forecast accuracy + Avg days in commit + WoW delta: ForecastingItem snapshots not in ETL
- Commit-risk "Owner" + "Days late" columns: need d_user join + row-context measure

**Cross-motion measure caveat:** `Total Open Pipeline Value` blends ARR (Land/Expand) and ACV (Renewal) into one column. Use ONLY for cross-motion comparison visuals like the Stage × Motion matrix. For any single-motion or motion-summable visual, keep using `Total Open Pipeline ARR` (L+E only) or `Total Renewal ACV Won` (Renewal-only) — the never-blend rule still applies.

**To rebuild:** `python3 -m scripts.sales.rw_compose_forecast`

## 2026-05-08 — REST-safe visual polish pass

Path chosen: **Path C — ship the cleanest possible Power BI report via REST**. Path A remains the highest-fidelity route for RAG-tinted card backgrounds and conditional formatting, but it still needs a Windows/PBI Desktop or browser-authored capture pass. Path B would hit the brainstorm mockup exactly, but changes the medium away from Fabric/Power BI.

**Shipped:**

- Added `build_textbox_visual` in `scripts/sales/_pbir_helpers.py` using the PBIR-Legacy textbox shape already present in the SalesManager fixture and workforce report builder.
- Registered `textbox` in `scripts/sales/_pbir_shapes.py` and removed it from `PENDING`.
- Re-composed **What Changed** with REST-safe section headers:
  - `RISK BAND - only what needs attention`
  - `CHANGE BUCKETS - comprehensive`
  - `DETAIL - top open opportunities by ARR impact`
- Re-composed **Forecast** with REST-safe section headers:
  - `HERO - quarter answer`
  - `STAGE X MOTION - open value matrix`
  - `FORECAST DISCIPLINE - movement quality`
  - `COMMIT RISK - late-stage open deals`
- Tightened both pages back inside the 1280x720 canvas. The previous Forecast commit-risk table extended below the page (`y=570, h=260`); it now ends at `y=705`.

**Live push evidence:**

- `python3 -m scripts.sales.rw_compose_what_changed` succeeded; What Changed now has 15 visuals.
- `python3 -m scripts.sales.rw_compose_forecast` succeeded; Forecast now has 13 visuals.
- `python3 -m scripts.sales.rw_validate --live` succeeded: 6 sections, 54 visualContainers, all measure refs resolve against 100 deployed measures.
- `python3 -m scripts.sales.rw_capture_visual --list --page "What Changed"` and `--page "Forecast"` confirm the textbox visualContainers are present in the live report.

**Still deferred:**

- RAG-tinted card backgrounds, combined count+ARR cards, and table cell conditional formatting. Do not hand-roll these `objects` blocks; capture a renderer-validated shape via PBI Desktop/Windows or a browser-authored Fabric edit, then generalize it.

**Tests:** `python3 -m pytest tests/sales` — 20 passed.
