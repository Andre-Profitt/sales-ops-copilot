# RW VP Ops Scorecard — Power BI build (browser)

This doc began as the curated browser-side build spec for Power BI Service. Current state: the semantic model is live with **106 DAX measures**, the Desktop lab PBIP has six KPI-targeted RW pages, and the current dashboard coverage truth table is generated at `docs/sales/RW_DASHBOARD_KPI_INTELLIGENCE.md`.

Source of truth for KPI definitions, targets, motion filters, and caveats: `scripts/sales/rw_kpi_graph.py`. Source of truth for current dashboard/page coverage, proxy status, missing measures, and next actions: `scripts/sales/rw_dashboard_intelligence.py`.

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

## 2026-05-09 — Parallels Power BI Desktop lab enabled

Path chosen: **Path A support lane**, with one adjustment. Do not depend on the
Windows VM accessing SimCorp-local data. Pull the live report definition from
Fabric on the Mac, place it in the Parallels shared folder as a PBIP-style
Desktop lab, then use Windows Power BI Desktop only for renderer-validated
formatting and shape capture.

**Shipped:**

- Installed Power BI Desktop in the `Windows 11` Parallels VM and verified
  `PBIDesktop.exe` at `C:\Program Files\Microsoft Power BI Desktop\bin\PBIDesktop.exe`.
- Added `scripts/sales/rw_pbi_desktop_lab.py`.
  - Regenerates `/Users/test/Downloads/rw-pbi-format-lab/rpt_vp_ops_scorecard_live_pbip/`
    from Fabric `getDefinition`.
  - Writes a minimal `.pbip` wrapper plus the live `definition.pbir`,
    `report.json`, and `.platform` parts.
  - Rewrites a small CSV fixture for isolated Desktop formatting experiments.
  - Can launch Desktop via an interactive Windows scheduled task with `--launch`.
- Added `docs/sales/RW_PBI_DESKTOP_FORMATTING_LAB.md` with the exact runbook,
  verified paths, capture targets, and deferred blockers.

**Verified:**

- Fabric `getDefinition` succeeds for `rpt_vp_ops_scorecard`.
- The live report definition currently contains only `definition.pbir`,
  `report.json`, and `.platform`.
- Power BI REST PBIX export is blocked with HTTP 403 for this tenant/report.
  Last captured request id: `7cd9881f-5899-435b-817a-700de204804d`.
- The VM can launch Power BI Desktop through Task Scheduler, but the VM was at
  the Windows lock screen during the PBIP-open test. Interactive formatting
  still requires signing into Windows.

**Decision record:**

- Path A remains the right next execution path because captured Desktop/Fabric
  shapes are the only low-risk route for RAG card backgrounds and table
  conditional formatting.
- Treat Desktop as a manual renderer/capture lab, not an automation surface.
  Parallels/macOS UI automation was not reliable enough for end-to-end clicking.
- Path B is still visually fastest but changes the medium away from Fabric.
  Path C already shipped the REST-safe polish; continuing to hand-roll unknown
  `singleVisual.objects` would be slower and riskier than capture.

**Next capture targets:**

- RAG card tint/accent/title/value/secondary-line shape.
- Combined count plus ARR card shape, if one Desktop visual can represent it
  cleanly.
- Table cell conditional-formatting shape for threshold-crossable columns.

## 2026-05-09 — Advanced Desktop-to-PBIR harness

Andre called out the real issue after opening the report in Desktop: the live
dashboard is still basically a valid wall of Power BI cards. The missing piece
was not more hand-authored measures; it was a proper Desktop-to-code harness for
advanced visual finish.

**Shipped:**

- Added `scripts/sales/rw_dashboard_harness.py`.
  - `snapshot` saves live/Desktop/path `report.json` plus inventory.
  - `inventory` writes visual inventory JSON/CSV with page, visual name, type,
    fields, object keys, coordinates, and stable hashes.
  - `audit` flags basic-finish gaps such as empty pages, plain cards, plain
    tables, and canvas overflow.
  - `diff` compares a pre-edit snapshot to the saved Desktop PBIP and can emit
    candidate visual/object JSON for promotion into `_pbir_shapes.py` and
    `_pbir_helpers.py`.
  - `extract` pulls a specific live/Desktop/path visual or just its
    `singleVisual.objects` block.
- Added `docs/sales/RW_ADVANCED_PBI_HARNESS.md` with the new capture workflow.

**Operating loop:**

1. `python3 -m scripts.sales.rw_dashboard_harness snapshot --source live --label before_rag_card`
2. Format one representative visual in Power BI Desktop.
3. Save the PBIP.
4. `python3 -m scripts.sales.rw_dashboard_harness diff --before output/rw_dashboard_harness/snapshots/before_rag_card.report.json --after-desktop --emit-candidates`
5. Promote the captured renderer-valid shape into the PBIR helpers/composers.

**Why this matters:**

- The prior REST-safe pass could only clean up layout and section labels.
- The Desktop lab alone proved the report could open, but did not make visual
  iteration systematic.
- This harness makes Desktop the renderer authority and Python the production
  compiler, which is the right path for RAG cards, combined cards, table
  conditional formatting, and richer matrix styling.

## 2026-05-09 — First RAG visual upgrade on What Changed

First enterprise-visual slice shipped against the live report. The initial
card-internal RAG object push was accepted by Fabric and visible in
`rw_capture_visual` as object-bearing cards, but the open Desktop copy stayed
stale and Power BI may still drop some card background/border subproperties at
render. To make the change visible and renderer-resilient, the risk band now
uses explicit tinted `basicShape` panels behind the card pairs.

**Shipped:**

- Added `build_rag_card_objects` and `build_rag_card_visual` in
  `scripts/sales/_pbir_helpers.py`.
  - Uses verified legacy-card typography object keys (`labels`,
    `categoryLabels`) from the SalesManager fixture.
  - Adds conservative `background` and `border` objects for card-level RAG
    treatment.
- Added `build_shape_visual` for static panel rectangles based on the verified
  `basicShape` shape from `tests/sales/fixtures/salesmanager_report.json`.
- Registered `basicShape` in `scripts/sales/_pbir_shapes.py` and removed it from
  `PENDING`.
- Updated `scripts/sales/rw_compose_what_changed.py` so the risk band now has:
  - At Risk panel: tint `#ffeeee`, accent `#cc3333`
  - Watch panel: tint `#fff8e6`, accent `#dd8800`
  - Healthy panel: tint `#eef9ee`, accent `#339933`
  - RAG object blocks attached to the six count/ARR cards.

**Live evidence:**

- `python3 -m scripts.sales.rw_compose_what_changed` succeeded.
- `python3 -m scripts.sales.rw_capture_visual --list --page "What Changed"`
  shows 18 visuals: 3 `basicShape` panels, 6 RAG object-bearing risk cards, 5
  change-bucket cards, 3 textboxes, and 1 detail table.
- `python3 -m scripts.sales.rw_validate --live` succeeded: 6 sections, 57
  visualContainers, all measure refs resolve against 100 measures.
- `python3 -m pytest tests/sales` succeeded: 27 passed.

**Note:**

The Desktop PBIP must be regenerated/reopened to inspect the latest live push.
An already-open Desktop copy will not update automatically.

## 2026-05-09 — Front page GraphRAG cleanup

Andre flagged the real visible problem: the `VP Ops Scorecard` front page still
looked like numbers sprawled across the canvas. The live audit confirmed it:
26 visuals, 23 plain cards, three slicers embedded in the grid, six cards
overflowing the 1280 x 720 canvas, and no decision hierarchy.

**GraphRAG read:**

- Source graph: `scripts/sales/rw_kpi_graph.py` with 31 RW target KPIs.
- Front page should retrieve only high-impact live signals from the graph, not
  display every KPI.
- ARR and ACV lanes remain separate. `Total Open Pipeline Value` is used only
  in the bottom portfolio map and is explicitly the cross-motion open-value
  measure.
- Missing/partial KPI graph items stay off the home page unless they explain a
  gap.

**Shipped:**

- Added `docs/sales/RW_FRONT_PAGE_GRAPHRAG_AUDIT.md`.
- Added `scripts/sales/rw_compose_scorecard_home.py`, an idempotent composer for
  the `VP Ops Scorecard` page.
- Replaced the old front page with:
  - left filter rail plus GraphRAG routing contract
  - top At Risk / Watch / Healthy operating-signal band
  - Growth ARR, Pipeline Discipline, and Renewal ACV KPI lanes
  - portfolio matrix by stage x motion
  - open-deal inspection table
- Added `tests/sales/test_rw_compose_scorecard_home.py`.

**Live evidence:**

- `python3 -m scripts.sales.rw_compose_scorecard_home` succeeded; old 26 visuals
  cleared and 52 structured visuals pushed.
- `python3 -m scripts.sales.rw_capture_visual --list --page "VP Ops Scorecard"`
  confirms 52 visuals: 16 `basicShape`, 19 `textbox`, 12 object-bearing cards,
  3 slicers, 1 matrix, and 1 table.
- `python3 -m scripts.sales.rw_validate --live` succeeded: 6 sections, 83
  visualContainers, all measure refs resolve against 100 measures.
- `python3 -m pytest tests/sales` succeeded: 28 passed.

**Remaining front-page visual debt:**

- The front-page table is still audit-flagged as a plain `tableEx`; capture a
  renderer-authored table formatting / conditional-formatting object block next.

## 2026-05-09 — Front page sophistication pass

The second front-page pass moved beyond layout cleanup into explicit graph-backed
context and table/matrix finish.

**Shipped:**

- Added conservative table/matrix formatting object helpers in
  `scripts/sales/_pbir_helpers.py`:
  - `build_table_style_objects`
  - `build_matrix_style_objects`
- Extended `build_table_visual` and `build_matrix_visual` to accept
  `singleVisual.objects` and `vcObjects`.
- Updated `scripts/sales/rw_compose_scorecard_home.py` so front-page lanes
  resolve KPI IDs from `scripts/sales/rw_kpi_graph.py`:
  - Growth ARR: `forecast_closed_won`, `opp_win_rate`
  - Pipeline Discipline: `pipeline_coverage_3x`, `stage_conversion`
  - Renewal ACV: `renewal_retention_rate`, `renewals_mom_trend`
  - Portfolio map: `stage_conversion`, `pipeline_coverage_3x`
  - Deal inspection: `opp_age`, `forecast_accuracy`
- Added target-context microcopy from the graph into each lane.
- Added framed bottom panels for the portfolio matrix and inspection table.

**Live evidence:**

- `python3 -m scripts.sales.rw_compose_scorecard_home` succeeded; front page now
  has 65 visuals.
- `python3 -m scripts.sales.rw_capture_visual --list --page "VP Ops Scorecard"`
  shows both the `pivotTable` and `tableEx` as object-bearing (`*cf*`).
- `python3 -m scripts.sales.rw_validate --live` succeeded: 6 sections, 96
  visualContainers, all measure refs resolve against 100 measures.
- `python3 -m scripts.sales.rw_dashboard_harness audit --source live --label front_page_sophisticated`
  no longer reports any front-page plain-card, plain-table, or canvas-overflow
  findings.
- `python3 -m pytest tests/sales` succeeded: 30 passed.

**Remaining report debt:**

- Forecast still has plain cards/table.
- What Changed still has plain change-bucket cards/table.
- Stage Hygiene, Renewals, and Growth Mix are still empty.

## 2026-05-09 — Front page consulting-pattern reset

Desktop validation exposed a renderer truth the JSON audit missed: the prior
front page was still not consulting grade because it depended on many short
20-28px textboxes. Power BI Desktop clipped them, so the page looked busy even
after the RAG/card styling pass.

**Pattern reset:**

- Reduced the front page from 69 visuals to 56 visuals.
- Removed standalone metric-label textboxes from KPI panels.
- Moved metric labels back into larger native card visuals:
  - risk cards are 82px tall
  - commercial-engine cards are 76px tall
  - native card category labels are shown again
- Kept only 18 standalone textboxes, all 34px+ high.
- Added a dark executive header band.
- Replaced the bottom matrix with a real `clusteredBarChart`:
  `Total Open Pipeline Value` by `stage_name`.
- Preserved the cardinal ARR/ACV rule:
  - Growth ARR uses Land + Expand ARR measures.
  - Renewal ACV uses Renewal-only ACV measures.
  - `Total Open Pipeline Value` appears only in the explicitly labeled
    cross-motion bottom chart/table context.

**Code shipped:**

- Added `build_clustered_bar_chart_visual` in `scripts/sales/_pbir_helpers.py`.
- Rebuilt `scripts/sales/rw_compose_scorecard_home.py` around:
  - dark title band
  - left filter / contract rail
  - three RAG exception panels
  - three commercial engine panels
  - open-value stage chart
  - deal inspection table
- Extended front-page tests to enforce:
  - 56 visuals
  - no card under 76px
  - no textbox under 34px
  - chart/table object blocks present

**Live evidence:**

- `python3 -m scripts.sales.rw_compose_scorecard_home` succeeded; front page now
  has 56 visuals.
- `python3 -m scripts.sales.rw_capture_visual --list --page "VP Ops Scorecard"`
  confirms 21 `basicShape`, 18 `textbox`, 12 object-bearing cards, 3 slicers,
  1 `clusteredBarChart`, and 1 `tableEx`.
- `python3 -m scripts.sales.rw_validate --live` succeeded: 6 sections, 87 total
  visualContainers, all measure refs resolve against 100 measures.
- `python3 -m scripts.sales.rw_dashboard_harness audit --source live --label front_page_consulting_v3`
  reports no front-page plain-card, plain-table, or canvas-overflow debt.
- `python3 -m pytest tests/sales` succeeded: 31 passed.

**Next visual debt:**

- Desktop auth must be stable before screenshot-gating every iteration.
- The bottom stage chart is intentionally simple; a future Desktop-authored
  version should add explicit axis/label tuning if the renderer accepts it.

## 2026-05-09 — Front page v4 exception-led pattern

Andre's read was right: v3 fixed clipping but still read too much like a
Power BI card layout. The v4 pass changes the pattern, not just the styling.

**What changed:**

- Rebuilt the front page from 56 visuals to 45 visuals.
- Replaced the three equal RAG panels with one executive exception strip:
  - `Exception ARR`
  - `Exception Opps Count`
  - At-risk / Watch / Forward supporting cards
- Added two chart-led diagnosis panels:
  - `Exception ARR` by `d_region[region]`
  - `Total Open Pipeline Value` by `f_opportunity[stage_name]`
- Moved operating KPIs into a compact pulse panel:
  - Won ARR
  - Win rate
  - Stage-forward %
  - Renewal retention
- Kept the named deal-inspection queue as the bottom-right action surface.

**Business-rule correction:**

The ARR exception family now explicitly filters `motion_type IN { "Land",
"Expand" }` for both counts and dollars. This prevents Renewal rows from
inflating counts while ARR exposure remains Land+Expand only.

New measures:

- `Exception Opps Count = [At Risk Opps Count] + [Watch Opps Count]`
- `Exception ARR = [At Risk Opps ARR] + [Watch Opps ARR]`

Live model now has 102 measures.

**Live evidence:**

- `python3 -m scripts.sales.rw_push_semantic_model` succeeded; model update LRO
  succeeded and refresh was enqueued.
- `python3 -m scripts.sales.rw_compose_scorecard_home` succeeded; front page now
  has 45 visuals and pre-flight resolved against 102 measures.
- `python3 -m scripts.sales.rw_capture_visual --list --page "VP Ops Scorecard"`
  confirms 15 `basicShape`, 14 `textbox`, 10 object-bearing cards, 3 slicers,
  2 `clusteredBarChart`, and 1 `tableEx`.
- `python3 -m scripts.sales.rw_validate --live` succeeded: 6 sections, 76 total
  visualContainers, all measure refs resolve against 102 measures.
- `python3 -m scripts.sales.rw_dashboard_harness audit --source live --label front_page_consulting_v4`
  reports no front-page plain-card, plain-table, or canvas-overflow debt.

## 2026-05-09 — Zebra BI lab direction

Zebra BI research and the lab proof plan are captured in
`docs/sales/RW_ZEBRA_BI_EVALUATION.md`. The downloaded PBIX/template graph and
RW element map are captured in
`docs/sales/RW_ZEBRA_BI_GRAPHRAG_ELEMENT_MAP.md`.

Decision:

- Test Zebra BI in the Desktop lab PBIP first, not the live report.
- Use `Zebra BI Tables` as the first proof because RW's weakest surface is the
  loose KPI/card-wall pattern; embedded variance tables should create the
  strongest consultant-grade improvement fastest.
- Use the Zebra `Sales Funnel` template as the pipeline/stage reference, the
  `Sales Dashboard` template as the front-page reference, `Daily Sales Flash`
  for `What Changed`, and `SaaS Sales` only for renewal/ARR-growth patterns.
- Promote only if the lab PBIP and Fabric render prove custom visuals,
  licensing, clipping, and ARR/ACV separation all hold.

## 2026-05-09 — Zebra BI Stage Hygiene lab proof

The first RW Zebra proof renders in Power BI Desktop against the live RW
semantic model.

**Harness shipped:**

- `scripts/sales/rw_zebra_template_miner.py`
  - Mines downloaded Zebra PBIX files for page, visual, projection-role, and
    object-setting patterns.
  - Drops `licenseSettings` from mined pattern output.
  - Emits sanitized CSV / JSONL / JSON artifacts for GraphRAG-style mapping.
- `build_zebra_bi_table_visual` in `scripts/sales/_pbir_helpers.py`
  - Builds Zebra BI Tables visuals with `config`, `query`, and `dataTransforms`
    blocks. The extra `query` / `dataTransforms` blocks are required; a visual
    with only `config.projections` renders as an empty shell.
- `scripts/sales/rw_apply_zebra_lab_proof.py`
  - Applies the local Stage Hygiene proof to the Desktop lab PBIP.
  - Copies Zebra custom visual packages from the downloaded Sales Funnel PBIX.
  - Supports local-only license injection via `ZEBRA_BI_LICENSE_KEY`; the key is
    not committed or written into repo docs/code.

**Desktop proof:**

- Lab PBIP:
  `/Users/test/Downloads/rw-pbi-format-lab/rpt_vp_ops_scorecard_zebra_lab_20260509_pbip/rpt_vp_ops_scorecard_zebra_lab.pbip`
- Page: `Stage Hygiene`
- Visual: Zebra BI Tables
- Category:
  - `f_stage_transition[from_stage_name]`
- Values:
  - `Stage Forward Pct (LE)`
  - `Stage Backward Pct (LE)`
  - `Avg Days In Prior Stage (LE)`
  - `Total Stage Transitions`
  - `Stage Moves ARR 7d`
- Screenshot evidence:
  `/Users/test/.frontier/artifacts/rw_zebra_stage_hygiene_lab_20260509.png`

**Verification:**

- `python3 -m pytest tests/sales/test_pbir_helpers.py tests/sales/test_rw_zebra_template_miner.py`
  passed: 17 tests.
- Desktop render after Parallels restart showed the Zebra table populated with
  RW stage rows and totals, no Zebra license popup.

## 2026-05-09 — Zebra BI Exceptions lab proof

The second RW Zebra proof renders in Power BI Desktop against the live RW
semantic model. This is the front-page candidate for replacing the current
sprawled exception cards with one executive exception table.

**Harness update:**

- `build_zebra_bi_table_visual` now uses Zebra's simple-table binding grammar:
  category and value projections are grouped under `Primary`. The earlier
  native-table-style `Primary` / `Secondary` split opened in Desktop as an
  empty Zebra shell.
- `scripts/sales/rw_apply_zebra_lab_proof.py` preserves existing local Zebra
  license settings in the Desktop lab when reapplying the proof, so the trial
  key does not need to be passed around after first activation.

**Desktop proof:**

- Lab PBIP:
  `/Users/test/Downloads/rw-pbi-format-lab/rpt_vp_ops_scorecard_zebra_lab_20260509_pbip/rpt_vp_ops_scorecard_zebra_lab.pbip`
- Page: `Zebra Exceptions`
- Visual: Zebra BI Tables
- Category:
  - `d_region[region]`
- Values:
  - `Exception ARR`
  - `Exception Opps Count`
  - `At Risk Opps ARR`
  - `Watch Opps ARR`
- Screenshot evidence:
  `/Users/test/.frontier/artifacts/rw_zebra_exceptions_lab_20260509.png`

**Verification:**

- `python3 -m pytest tests/sales/test_pbir_helpers.py tests/sales/test_rw_zebra_template_miner.py`
  passed: 17 tests.
- Local repo secret scan over `scripts/sales`, `tests/sales`, and `docs/sales`
  passed: no Zebra trial token substring found.
- Desktop render after Power BI restart showed the Zebra table populated with
  RW region rows and totals, no Zebra license popup.
- Business-rule check: `Exception ARR`, `At Risk Opps ARR`, and `Watch Opps ARR`
  are Land+Expand ARR measures only. Renewal ACV is not present in this visual;
  `Total Open Pipeline Value` remains the only explicitly labeled cross-motion
  measure elsewhere.

**Next proof:**

Promote Zebra BI Tables into the actual VP Ops front-page redesign only after
the production page layout is rebuilt around: one exception spine, one pipeline
movement spine, and compact RAG scorecards. Do not keep the current wall of
cards and merely swap visual types.


## VP Ops Scorecard front-page spine rebuild — PR1 (2026-05-09)

PR1 of the spine rebuild replaces the 45-visualContainer card wall with two
spines + a 4-card KPI strip. Exception spine uses Codex's lab-proven Zebra BI
Tables binding pattern (commit `303bc6b`) lifted into
`scripts/sales/rw_compose_scorecard_home.py:_build_exception_spine`. Movement
spine is a textbox placeholder pending PR2's ARR-7d measure authoring.

**Layout (sums to 720):**

| Zone                            | y   | h   |
| ------------------------------- | --- | --- |
| Page title (textbox)            | 0   | 64  |
| Exception spine (Zebra Tables)  | 80  | 264 |
| Movement-spine placeholder      | 360 | 224 |
| KPI strip (4 native cards)      | 600 | 120 |

**Bindings:**

- Exception spine values (positional, locked by
  `test_exception_spine_value_order_matches_lab_proof`):
  `Exception ARR`, `Exception Opps Count`, `At Risk Opps ARR`,
  `Watch Opps ARR`. All Land+Expand only — `motion_type IN { "Land", "Expand" }`
  is enforced at the deployed-measure layer.
- KPI strip measures: `Total Closed Won ARR` (f_opportunity),
  `Win Rate ARR` (f_opportunity), `Stage Forward Pct (LE)` (f_stage_transition),
  `Renewal Retention Pct (Period)` (f_opportunity). The retention card is
  Renewal-side ACV; cardinal rule preserved (compute layer, not display layer).

**Verification:**

- `python3 -m pytest tests/sales/` → all sales tests passing (10 new + 54
  pre-existing).
- Live report id `d7362a11-f3dd-4bd1-a69a-68c941c2598b` in workspace
  `b66233d5-9d4a-44ba-89a8-b70206d98ae7`. Pre-flight resolved all measure
  refs against 102 deployed measures.
- Pre-push snapshot of the 45-visual state preserved at
  `~/.frontier/artifacts/rw_vpops_pre_pr1_20260509.json` (rollback-safe).

**Live promote entry point:**

The correct CLI is `python3 -m scripts.sales.rw_compose_scorecard_home`
(fetches → composes → pushes the full report.json). `rw_push_report.py:deploy()`
is a *bootstrap-only* script that pushes a minimal empty report — using it for
the spine push will wipe the page. The plan originally pointed at
`rw_push_report.py`; learned this the hard way during PR1 deploy and rolled
back from snapshot. Future RW front-page deploys must use
`rw_compose_scorecard_home`.

**Deferred to PR2:**

- Movement waterfall — needs 4 new ARR-7d measures: `New Opps ARR 7d`,
  `Closed Won ARR 7d`, `Closed Lost ARR 7d`, `Backward Moves ARR 7d`.
- Gate-violation exception column — needs 1 new measure
  `Commercial Approval Gate Exception ARR` joining f_opportunity to
  `Stage_20_Approval__c`. sfkg confirms 257 SF reports / 28 dashboards already
  use that field, so the underlying data is sound.
- Zebra Cards binding pattern — current PR1 strip uses native cards; sparklines
  + variance arrows wait for the Cards binding to be authored against the live
  semantic model.


## Zebra Template Bulk Conversion Audit — 2026-05-09

The 20-template Fabric bulk publish succeeded mechanically, but failed the
polish gate. Treat the output as a native-approximation harness, not as a
template-fidelity conversion.

Artifacts:

- Publisher: `scripts/sales/rw_zebra_kg_publish_all_templates.py`
- TMDL emitter: `scripts/sales/rw_zebra_kg_tmdl_emit.py`
- Conversion audit: `scripts/sales/rw_zebra_kg_conversion_audit.py`
- Audit report: `docs/sales/RW_ZEBRA_NATIVE_CONVERSION_AUDIT.md`
- Review memo: `docs/sales/RW_ZEBRA_NATIVE_CONVERSION_REVIEW.md`

Audit result: source Zebra PBIX corpus has 195 pages and 1,729 visualContainers.
The current native bridge uses 360 mined Zebra visualContainers and drops 1,369
non-Zebra context visualContainers. After the page-preserving fix, native output
has 0 unresolved measure refs and 0 off-canvas visuals, but it is only 20.8%
source-visual coverage.

Decision: do not bulk-republish this path as "polished." Next work is either a
Zebra-fidelity lab that preserves full PBIX `Report/Layout` and custom visual
packages, or a smaller RW-native redesign that deliberately lifts selected Zebra
patterns into the VP Ops dashboard.


## Zebra Fidelity Lab - Sales Funnel Specimen — 2026-05-09

The bridge is now narrowed to one high-fidelity specimen:
`sales-funnel-power-bi-template`.

Reference doc: `docs/sales/RW_ZEBRA_FIDELITY_LAB_SALES_FUNNEL.md`.

Live lab report:
https://app.fabric.microsoft.com/groups/b66233d5-9d4a-44ba-89a8-b70206d98ae7/reports/02edc230-461b-4ffb-b1cc-cb9e067fa66a

Engineering gate:

- Source PBIX: 6 pages, 104 visualContainers, 19 resource parts.
- Published report: `zbr_fidelity_sales-funnel-power-bi-template`.
- Published semantic model: `sm_zbr_fidelity_sales-funnel-power-bi-template`.
- Live round-trip verify: 6/6 pages, 104/104 visuals, 19/19 resources,
  semantic model binding present.

Correct command:

```bash
.venv/bin/python -m scripts.sales.rw_zebra_kg_fidelity_publish \
  --verify-live \
  --template sales-funnel-power-bi-template
```

Scale rule: do not add more Zebra templates until this one passes visual review
in Fabric/Desktop. The learning target is renderer fidelity and reusable bridge
rules, not bulk count.


## Zebra Native Layout Bridge - Sales Funnel — 2026-05-09

Andre correctly flagged that full Zebra custom-visual fidelity can still be
blocked by SimCorp tenant policy. The SimCorp-safe bridge is therefore
**native layout**:

- preserve full source PBIX page layout and non-Zebra page furniture
- translate only Zebra custom visual containers into native Power BI visuals
- remove `CustomVisuals/*` report definition parts and custom visual packages

Reference doc: `docs/sales/RW_ZEBRA_NATIVE_LAYOUT_SALES_FUNNEL.md`.

Live native-layout report:
https://app.fabric.microsoft.com/groups/b66233d5-9d4a-44ba-89a8-b70206d98ae7/reports/7483393a-17ff-42e8-9e46-97a425cd6b94

Engineering gate:

- Published report: `zbr_native_layout_sales-funnel-power-bi-template`.
- Published semantic model: `sm_zbr_native_layout_sales-funnel-power-bi-template`.
- Source/native local gate: 6/6 pages, 104/104 visuals, 20 Zebra custom visuals
  translated, 0 fallback textboxes, 13 static resources, 0 custom visual
  leftovers, 0 custom resource parts.
- Live round-trip verify: 6/6 pages, 104/104 visuals, 13/13 static resources,
  0 custom resources, 0 custom visual leftovers, semantic model binding present.

Correct command:

```bash
.venv/bin/python -m scripts.sales.rw_zebra_kg_native_layout_publish \
  --verify-live \
  --template sales-funnel-power-bi-template
```


## Desktop Lab Checkpoint — 2026-05-09

The local Zebra lab PBIP is open in Power BI Desktop under Parallels and is
connected live to `sm_sales_kpis_rw`.

Lab PBIP:

```text
C:\Mac\Home\Downloads\rw-pbi-format-lab\rpt_vp_ops_scorecard_zebra_lab_20260509_pbip\rpt_vp_ops_scorecard_zebra_lab.pbip
```

Evidence:

- Applied the current lab proof with `python3 -m scripts.sales.rw_apply_zebra_lab_proof`.
- Validated the generated report JSON with
  `python3 -m scripts.sales.rw_validate --file ~/Downloads/rw-pbi-format-lab/rpt_vp_ops_scorecard_zebra_lab_20260509_pbip/rpt_vp_ops_scorecard.Report/report.json`.
- Validation result: 7 sections, 44 total visualContainers, all measure refs
  resolve against 102 deployed measures.
- Desktop screenshot:
  `~/.frontier/artifacts/rw_vpops_lab_open_connected_20260509.png`.
- The PBIP contains `VP Ops Scorecard` with 7 visualContainers, but Desktop
  opened on the `Zebra Exceptions` proof page. The next renderer gate is to
  navigate to `VP Ops Scorecard`, capture that page, and judge whether the
  7-visual spine is actually consultant-grade.

Power BI Modeling MCP status:

- Windows-side MCP install is good and `tools/list` works.
- The PBIP uses a live Fabric semantic-model connection, not an imported local
  Desktop database, so the local Desktop Analysis Services workspace still shows
  `DbCount=0`.
- `ConnectFabric` from Codex-through-`prlctl` does not complete because that MCP
  process runs outside the logged-in Desktop user context. Use a Windows-side
  interactive MCP client for semantic-model edits, or continue using the
  repo's Fabric REST validation path for this lab.


## RW KPI Targeting Pass - All Pages (2026-05-09)

Andre's review after the native/Zebra lab pass: the visuals were directionally
better, but the report still needed every tab rebuilt against the actual RW KPI
contract rather than generic dashboard furniture.

**Shipped in code:**

- Added `scripts/sales/rw_page_kpi_contract.py` as the page-level contract:
  every production tab declares its job, RW KPI IDs, required deployed
  measures, motion lane, and caveat.
- Added `scripts/sales/rw_compose_all_pages.py` as the all-tab compiler. It
  rebuilds:
  - `VP Ops Scorecard`
  - `What Changed`
  - `Forecast`
  - `Stage Hygiene`
  - `Renewals`
  - `Growth Mix`
- Added native KPI-targeted composers for the previously weak/empty tabs:
  `rw_compose_stage_hygiene.py`, `rw_compose_renewals.py`, and
  `rw_compose_growth_mix.py`.
- Updated `scripts/sales/rw_apply_zebra_lab_proof.py` so the Desktop lab PBIP
  now applies all KPI-targeted native pages, while preserving the separate
  `Zebra Exceptions` proof page.
- Reworked the front page into a 25-visual native layout:
  KPI strip, exception spine, open ARR by stage, stage hygiene matrix, and
  7-day movement pulse.

**Business-rule guardrails:**

- `Renewals` is Renewal ACV only.
- `Growth Mix` is Land+Expand ARR only.
- `Forecast` is the only page that contains `Total Open Pipeline Value`, and it
  is explicitly the cross-motion value measure.
- `VP Ops Scorecard` may place renewal retention beside ARR KPIs, but it does
  not blend Renewal ACV into ARR.

**Desktop lab output:**

```text
/Users/test/Downloads/rw-pbi-format-lab/rpt_vp_ops_scorecard_zebra_lab_20260509_pbip/rpt_vp_ops_scorecard.Report/report.json
```

Page counts after regeneration:

| Page | VisualContainers |
| --- | ---: |
| Zebra Exceptions | 3 |
| Stage Hygiene | 18 |
| Forecast | 13 |
| Growth Mix | 14 |
| Renewals | 14 |
| What Changed | 18 |
| VP Ops Scorecard | 25 |

Total: 7 sections, 105 visualContainers.

**Verification:**

- `python3 -m scripts.sales.rw_apply_zebra_lab_proof` succeeded and backed up
  the prior lab report JSON.
- `python3 -m scripts.sales.rw_validate --file ~/Downloads/rw-pbi-format-lab/rpt_vp_ops_scorecard_zebra_lab_20260509_pbip/rpt_vp_ops_scorecard.Report/report.json`
  succeeded: all measure refs resolve against 102 deployed measures.
- Contract validation passed: all declared RW KPI measures are present on their
  target pages.
- `.venv/bin/pytest tests/sales -q` succeeded: 167 passed, 1 skipped.

**Promotion status:**

This checkpoint updates the local Desktop lab and repo compiler only. The live
production RW report was not pushed in this pass; promote with
`python3 -m scripts.sales.rw_compose_all_pages` after Desktop visual review.


## Zebra Native Polish Pass v1 - Plain Visual Debt Removed (2026-05-09)

Follow-up to the all-page KPI targeting pass. The page inventory showed the
remaining "old Power BI" feel was concentrated in `Forecast` and `What Changed`:
plain cards and unstyled `tableEx` visuals, while the newer pages already used
object-bearing cards/tables.

**Shipped:**

- Replaced all plain `Forecast` cards with object-bearing native RAG cards.
- Added renderer-safe matrix/table styling objects to the `Forecast` stage x
  motion matrix and commit-risk table.
- Replaced all plain `What Changed` change-bucket cards with object-bearing
  native RAG cards.
- Added renderer-safe table styling objects to the `What Changed` detail table.
- Added a test gate that runs the dashboard harness audit against the compiled
  target pages and fails on `[plain-card]` or `[plain-table]` findings.

**Lab audit result:**

```bash
python3 -m scripts.sales.rw_dashboard_harness audit \
  --source path \
  --path ~/Downloads/rw-pbi-format-lab/rpt_vp_ops_scorecard_zebra_lab_20260509_pbip/rpt_vp_ops_scorecard.Report/report.json \
  --label rw_kpi_lab_zebra_polish_v1
```

Result: `no findings`.

**Verification:**

- `python3 -m scripts.sales.rw_apply_zebra_lab_proof` regenerated the Desktop
  lab PBIP report JSON.
- `python3 -m scripts.sales.rw_validate --file ~/Downloads/rw-pbi-format-lab/rpt_vp_ops_scorecard_zebra_lab_20260509_pbip/rpt_vp_ops_scorecard.Report/report.json`
  succeeded: all refs resolve against 102 deployed measures.
- `.venv/bin/pytest tests/sales -q` succeeded: 168 passed, 1 skipped.

**Remaining polish gate:**

The code-level visual debt gate is now clean. The next gate is Desktop
screenshot review for spacing, clipping, and whether the native Zebra-pattern
pages actually read at consulting grade.


## Last-Four Tab Enterprise Polish v2 - Open Pipeline Fix (2026-05-10)

Andre flagged two material issues after Desktop review: `Renewals` and
`Growth Mix` were visually better but showing zero/weak values, and the last
four tabs still read too generic.

**Root cause:**

- `Renewals` was leading with closed-won Renewal ACV. Current-year data has
  meaningful open Renewal ACV, so a closed-won-first page can read as zero in
  the wrong filter context.
- `Growth Mix` was leading with closed-won Land/Expand ARR. Current-year growth
  review is more useful as open Land/Expand pipeline.
- `Partner ARR` used exact `lead_source = "Partner"`, but the live data includes
  partner-like values such as `Limited Partner`; exact matching undercounted.

**Live data check from OneLake `f_opportunity`:**

- 2026 open Renewal ACV: approximately `151.6M`.
- 2026 open Land ARR: approximately `175.2M`.
- 2026 open Expand ARR: approximately `141.0M`.
- Partner-like open L+E ARR exists under lead-source strings containing
  `partner`.

**Semantic model changes deployed to `sm_sales_kpis_rw`:**

- Added `Total Open Renewal ACV`.
- Added `Total Renewal ACV Due`.
- Added `Open Land ARR`.
- Added `Open Expand ARR`.
- Updated `Partner ARR` to use
  `CONTAINSSTRING(LOWER(f_opportunity[lead_source]), "partner")` while keeping
  the Land+Expand ARR and open-pipeline filters.

The model now has 106 deployed measures. Fabric updateDefinition LRO succeeded
for semantic model `3c58b5dd-b321-4aaa-a5cd-fb73e474edbb`; refresh was
enqueued.

**Page changes:**

- `Renewals` now leads with open renewal exposure:
  `Total Open Renewal ACV`, retention, won ACV, lost ACV.
- `Renewals` regional chart now uses `Total Open Renewal ACV`, not closed-won
  ACV.
- `Growth Mix` now leads with `Open Land ARR`, `Open Expand ARR`, partner ARR,
  and partner percentage.
- `Growth Mix` regional chart now uses `Total Open Pipeline ARR`.
- Forecast, What Changed, and Stage Hygiene labels were tightened to more
  executive/operating language and away from generic generated-section wording.

**Verification:**

- `python3 -m scripts.sales.rw_apply_zebra_lab_proof` regenerated the Desktop
  lab PBIP report JSON.
- `python3 -m scripts.sales.rw_validate --file ~/Downloads/rw-pbi-format-lab/rpt_vp_ops_scorecard_zebra_lab_20260509_pbip/rpt_vp_ops_scorecard.Report/report.json`
  succeeded: 7 sections, 105 visualContainers, all refs resolve against 106
  deployed measures.
- `python3 -m scripts.sales.rw_dashboard_harness audit --source path --path ~/Downloads/rw-pbi-format-lab/rpt_vp_ops_scorecard_zebra_lab_20260509_pbip/rpt_vp_ops_scorecard.Report/report.json --label rw_last4_enterprise_polish_v2`
  returned `no findings`.
- Contract validation returned zero errors.
- `.venv/bin/pytest tests/sales -q` succeeded: 170 passed, 1 skipped.

**Promotion status:**

The semantic model is live with the new measures. The report layout changes are
currently applied to the local Desktop lab PBIP; promote to the live RW report
with `python3 -m scripts.sales.rw_compose_all_pages` after Desktop visual
review.


## RW Dashboard KPI Intelligence Matrix - 2026-05-10

Andre's next review theme: the dashboard is improving visually, but it still
needs sharper intelligence on whether all 31 RW KPIs are genuinely covered or
only implied by generic/proxy visuals.

**Shipped:**

- Added `scripts/sales/rw_dashboard_intelligence.py`.
- Generated `docs/sales/RW_DASHBOARD_KPI_INTELLIGENCE.md`.
- Generated `docs/sales/RW_DASHBOARD_KPI_INTELLIGENCE.json`.

**Current coverage rollup:**

| Status | Count |
| --- | ---: |
| Cleanly surfaced on dashboard pages | 14 |
| Surfaced but still proxy/incomplete | 6 |
| Model-available but not clearly surfaced | 3 |
| Partial data or measure gap | 3 |
| Source-data gap | 5 |
| Total RW KPIs | 31 |

**Most important correction:**

`pipeline_coverage_3x`, `forecast_accuracy`, `stage3_approvals_compliance`,
`existing_arr_run_rate`, `indexation_arr_growth`, and `synergy_deals_won` are
now explicitly marked `surfaced_partial`, not cleanly done. This prevents the
dashboard from looking complete just because a page name or proxy measure
mentions the KPI.

**Next upgrade lanes:**

- Fast page-only wins: surface `sales_cycle_length`,
  `closed_won_avg_deal_size`, and `lost_arr_quarterly`.
- Semantic/model work: add true pipeline coverage ratio, ForecastingItem
  accuracy, Commercial Approval compliance, synergy measures, existing ARR
  run-rate, indexation, business-at-risk, and SaaS YoY.
- Source/ETL work: value tier, Commercial Approval close timing,
  Axioma/acquired cross-sell, one-off revenues, and PS attach.

ARR remains Land+Expand only, Renewal ACV remains Renewal only. The only
allowed cross-motion value measure is still `Total Open Pipeline Value`.

**Verification:**

- `python3 -m scripts.sales.rw_dashboard_intelligence` regenerated the
  markdown and JSON matrix.
- `.venv/bin/pytest tests/sales -q` succeeded: 178 passed, 1 skipped.


## RW Fast KPI Coverage Upgrade - 2026-05-10

Follow-up to the intelligence matrix. The prior rollup still had three
model-ready KPIs not clearly surfaced. Those should not stay in the backlog
when the model already has the measures.

**Shipped:**

- Added `sales_cycle_length` to `Stage Hygiene` with `Land Avg Sales Cycle Days`
  and `Avg Sales Cycle Days` cards.
- Added `closed_won_avg_deal_size` to `Growth Mix` with an `Avg Deal Size Won`
  KPI card and detail-table column.
- Promoted `lost_arr_quarterly` to the `Renewals` KPI contract; the page already
  carried `Total Renewal ACV Lost`, now it counts as intentional KPI coverage.

**Updated intelligence rollup:**

| Status | Before | After |
| --- | ---: | ---: |
| Cleanly surfaced on dashboard pages | 14 | 17 |
| Surfaced but still proxy/incomplete | 6 | 6 |
| Model-available but not clearly surfaced | 3 | 0 |
| Partial data or measure gap | 3 | 3 |
| Source-data gap | 5 | 5 |
| Total RW KPIs | 31 | 31 |

**Page counts after composition:**

| Page | VisualContainers |
| --- | ---: |
| Stage Hygiene | 19 |
| Renewals | 14 |
| Growth Mix | 15 |

ARR/ACV separation is unchanged: `Stage Hygiene` and `Growth Mix` use
Land+Expand ARR/process measures, `Renewals` uses Renewal ACV only.

**Lab verification:**

- `python3 -m scripts.sales.rw_apply_zebra_lab_proof` regenerated the local
  Desktop PBIP.
- `python3 -m scripts.sales.rw_validate --file ~/Downloads/rw-pbi-format-lab/rpt_vp_ops_scorecard_zebra_lab_20260509_pbip/rpt_vp_ops_scorecard.Report/report.json`
  succeeded: 7 sections, 107 visualContainers, all refs resolve against 106
  deployed measures.
- `python3 -m scripts.sales.rw_dashboard_harness audit --source path --path ~/Downloads/rw-pbi-format-lab/rpt_vp_ops_scorecard_zebra_lab_20260509_pbip/rpt_vp_ops_scorecard.Report/report.json --label rw_fast_kpi_coverage_upgrade`
  returned `no findings`.
- `.venv/bin/pytest tests/sales -q` succeeded: 178 passed, 1 skipped.


## What Changed Movement Ledger + Zebra Transfer Gate - 2026-05-10

Follow-up to the visual QA wall-of-cards finding on `What Changed`.

**Shipped:**

- Replaced the five 7-day movement micro-cards with one styled movement ledger
  table covering stage moves, stage move ARR, new opps, won, and lost.
- Preserved the top RAG risk-band KPI strip and ARR/ACV separation guardrails.
- Added a regression test that fails if `What Changed` returns to
  medium-or-higher visual QA debt.
- Added the local Zebra transfer framework:
  - `scripts/sales/rw_zebra_transfer_dna.py`
  - `scripts/sales/rw_zebra_transfer_rebuilder.py`
  - `docs/sales/RW_ZEBRA_TRANSFER_FRAMEWORK.md`
- Sanitized Zebra transfer DNA so license/activation object groups are not
  persisted in generated artifacts.

**Verification:**

- `python3 -m scripts.sales.rw_apply_zebra_lab_proof` regenerated the local
  Desktop PBIP.
- `python3 -m scripts.sales.rw_validate --file ~/Downloads/rw-pbi-format-lab/rpt_vp_ops_scorecard_zebra_lab_20260509_pbip/rpt_vp_ops_scorecard.Report/report.json`
  succeeded: 7 sections, 103 visualContainers, all refs resolve against 106
  deployed measures.
- `python3 -m scripts.sales.rw_dashboard_harness audit --source path --path ~/Downloads/rw-pbi-format-lab/rpt_vp_ops_scorecard_zebra_lab_20260509_pbip/rpt_vp_ops_scorecard.Report/report.json --label final_lab`
  returned `no findings`.
- `python3 -m scripts.sales.rw_dashboard_harness visual-qa --source path --path ~/Downloads/rw-pbi-format-lab/rpt_vp_ops_scorecard_zebra_lab_20260509_pbip/rpt_vp_ops_scorecard.Report/report.json --label final_lab --fail-on medium --markdown docs/sales/RW_DASHBOARD_VISUAL_QA.md`
  returned 0 findings.
- `python3 -m scripts.sales.rw_zebra_transfer_rebuilder --template sales-funnel-power-bi-template`
  passed its transfer gate: 6/6 pages, 107/104 visualContainers, no custom
  leftovers, no fallback textboxes, no lost Zebra visuals, no unresolved measure
  refs.
- `python3 -m pytest tests/sales -q` succeeded: 198 passed, 1 skipped,
  2 warnings.
## 2026-05-10 — RW KPI decision-coverage hardening

This pass tightened the native RW dashboard around Richard Wyeth's actual VP Ops KPI set rather than broad visual styling. No Fabric publish was performed.

**Decision contract shipped:**

- `scripts/sales/rw_page_kpi_contract.py` now defines an executable page-by-page target map for the six RW pages:
  - VP Ops Scorecard
  - What Changed
  - Forecast
  - Stage Hygiene
  - Renewals
  - Growth Mix
- Each page declares:
  - executive question
  - primary KPIs
  - secondary diagnostics
  - required visual role per KPI
  - motion guardrail (`land_expand_arr`, `renewal_acv`, `cross_motion_labeled`, or `process`)
  - data status (`clean`, `proxy`, `partial`, `missing model measure`, `missing source data`)
- `rw_compose_all_pages.py` now composes the full six-page local report shape and runs the decision contract before push-capable code paths.

**Regression gates added:**

- Missing required primary KPI fails.
- Wrong ARR/Renewal ACV motion fails.
- Cross-motion measures fail unless explicitly labeled.
- Proxy/gap KPIs fail if counted as clean.
- Required KPI visual role fails if the composed page places the measure on the wrong native visual type.

**Small page-copy improvements:**

- Forecast proxy cards are labeled as proxy until a true Forecast Accuracy / snapshot measure exists.
- Stage Hygiene Stage 3 compliance card is labeled as proxy until Commercial Approval compliance is modeled.

**Business rule preserved:** ARR remains Land + Expand only; Renewal ACV remains Renewal-only. `Total Open Pipeline Value` is the only explicitly labeled cross-motion value measure.
## 2026-05-10 — What Changed Zebra-native transfer application

Applied the deeper Zebra visual-DNA grammar to the real RW `What Changed` page only.  The top exception band still uses the same ARR-only risk measures, but each card now carries explicit Zebra-derived native card object metadata (`stylePreset.source = zebra-visual-dna`) on top of the existing RAG background/border/label treatment.  The 7-day movement ledger remains a native `tableEx`, not a card wall, and now uses the reusable compact movement-ledger object grammar with Zebra column-grammar lineage and data-bar hints.  The open movement queue keeps its native detail table role with the same supported fields/measures and a reusable detail-ledger style.

No Fabric publish was performed.  This is intentionally a one-page proof that Zebra extraction can improve RW native emitters without reintroducing custom visuals or blending ARR/Renewal ACV guardrails.

## 2026-05-10 — Stage Hygiene Zebra-native transfer application

Applied the proven Zebra-native grammar pattern to exactly one additional RW page: `Stage Hygiene`.

**Shipped:**

- Kept the required Stage Hygiene KPI contract intact: forward rate, backward rate, stage aging, Land cycle, L+E cycle, Stage Conversion Matrix, and the Stage 3 forward proxy all remain present.
- Replaced the Stage Hygiene hero/process cards with object-bearing native card grammar (`stage-hygiene-process-kpi-card`) using the same safe Zebra visual-DNA lineage metadata as the What Changed proof.
- Converted the Stage Conversion Matrix into a native `tableEx` diagnostic table in IBCS order: stage, forward %, backward %, average days, moves, and 7-day ARR moved.
- Added native data-bar metadata only to the supported `Stage Moves ARR 7d` measure to carry Zebra marker/scale intent without inventing unsupported variance fields.
- Kept Stage 4 Bottleneck Detail as a dense native detail-ledger table with Zebra/IBCS column grammar.
- Did not broaden the change to Forecast, Renewals, or Growth Mix.

**Lab verification:**

- `python3 -m scripts.sales.rw_apply_zebra_lab_proof` regenerated the local Desktop PBIP.
- `python3 -m scripts.sales.rw_dashboard_harness visual-qa --source path --path ~/Downloads/rw-pbi-format-lab/rpt_vp_ops_scorecard_zebra_lab_20260509_pbip/rpt_vp_ops_scorecard.Report/report.json --label rw_stage_hygiene_zebra_native --fail-on medium --markdown docs/sales/RW_DASHBOARD_VISUAL_QA.md` returned 0 findings.
- Focused contract tests now assert Stage Hygiene native visual types, no medium+ visual QA debt, object-bearing card grammar, and Zebra/IBCS table grammar.

No Fabric publish was performed.  ARR remains Land+Expand only, Renewal ACV remains Renewal only, and no custom visuals were introduced to the native Stage Hygiene page.

