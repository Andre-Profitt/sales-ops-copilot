# RW VP Ops Scorecard — Redesign Spec

**Date:** 2026-05-08
**Owner:** Andre
**Audience:** Richard Wyeth (MD Sales Operations) — personal exec view, opens 1×/day
**Target:** `rpt_vp_ops_scorecard` (`d7362a11-f3dd-4bd1-a69a-68c941c2598b`) in workspace `b66233d5-9d4a-44ba-89a8-b70206d98ae7`
**Semantic model:** `sm_sales_kpis_rw` (`3c58b5dd-b321-4aaa-a5cd-fb73e474edbb`)

## Problem

Current report has 26 visuals on a single page — "numbers all over the place." All KPI cards, no tables, no information hierarchy. RW can see everything but can't act on anything.

## Design principles

1. **One job per page.** RW does four distinct jobs; give each a tab.
2. **Tables, not card walls.** When the data is N rows × M columns (stage transitions, region splits, commit risk), it goes in a table. Cards are reserved for single-number "how much" answers.
3. **Risk first, comprehensive below.** Every page leads with what needs attention, then provides the full data underneath.
4. **Power-user density.** RW knows the metrics. No exec eye-candy. Optimize for information per pixel.

## Information architecture

Four tabs at the bottom of the report. Default landing: **What Changed**.

| Tab | Job | Lead question |
|---|---|---|
| **What Changed** | Daily delta review | "What moved since I last looked?" |
| **Forecast** | Quarterly attainment | "Are we going to make the number?" |
| **Stage Hygiene** | Funnel diagnosis | "Where is the funnel leaking?" |
| **Renewals** | Retention pulse | "What's at risk of churning?" |

**Cross-page slicers:** region (multi-select), motion (Land/Expand/Renewal), fiscal quarter. Power BI slicers are per-page; use the **Sync Slicers** feature (set in `report.json` via `slicerSyncGroups` or per-visual `syncGroup`) so a selection on one tab carries to the others. Place them in a top-row band on each tab.

## Tab 1 — What Changed (landing)

**Window slicer:** since yesterday | since Monday | since FQ start

### Risk band (top, hero)
Three colored cards summarizing change classification:
- **At risk** — Stage 5+ deals slipped or moved backward (count, ARR exposure)
- **Watch** — Stage 3-4 stalls (>14d no movement) (count, ARR)
- **Healthy** — Forward progressions, new opps, won (count, ARR)

### Change buckets (middle)
Four counter cards with direction arrows:
- **Stage moves** — count, forward vs backward split, ARR moved
- **Slips** — close-date push count, ARR pushed out of FQ
- **New opps** — count, ARR added
- **Closed** — won/lost split, ARR delta

### Detail table (bottom)
Top 20 changes by ARR impact: Opp · Owner · Region · Change · ARR · When · Risk class. Opp column rendered as Salesforce URL (`https://simcorp.my.salesforce.com/<Id>`) — click opens the record in a new tab. (Native PBI drill-through pages are Phase 2.)

**Data dependency:** OpportunityFieldHistory (already in `sf_to_fabric_rw_phase2.py`). Need new measures for window-bound aggregations.

## Tab 2 — Forecast

### Hero (top)
Three cards:
- **Quota attainment forecast** (large) — closed-won + weighted pipeline / quota, with stacked progress bar (closed-won / weighted / gap)
- **Pipeline coverage** — open ARR / quota, RAG vs 3× target
- **Days remaining in FQ** — with avg-cycle context ("38% of pipe could close in time")

### Stage × motion matrix (middle)
**This is the table replacement for the 6 motion-breakout cards.** Rows = stages 3-6; columns = Land ARR / Expand ARR / Renewal ACV / Total open / Weighted. Total row at bottom.

### Two side-by-side compact tables
- **Region split:** Region · Coverage × · Weighted ARR (RAG on coverage)
- **Forecast discipline:** Slips this FQ · Upgrades · Avg days in commit · Forecast accuracy last FQ (each with week-over-week delta)

### Commit-risk table (bottom)
Top 10 late-stage open deals: Opp · Owner · Stage · ARR · Close · Days late · Last move.

**Data dependency:** existing semantic model + `Quota__c` if available (else parameterize per-region quotas in DAX).

## Tab 3 — Stage Hygiene

### Stage matrix (top, hero)
**Replaces the 6 per-stage forward-rate cards.** Rows = each transition (S1→S2 through S6→Won). Columns: Forward % (RAG) · Backward % · Avg days in stage · Open count · Open ARR · Note.

Note column flags S3→S4 and S4→S5 as partial-population (per `project_simcorp_funnel_skip_2026-05-06.md` — ~70% of close-wons skip Stage 4).

### Two side-by-side visuals (middle)
- **Conversion funnel chart:** stage-by-stage retention as a tapered funnel (visual context for the matrix)
- **Where deals die:** loss count + ARR by stage at loss; % of total losses

### Stall coaching table (bottom)
Open opps with no movement >14 days, top 15 by ARR: Opp · Owner · Region · Stage · ARR · Days stalled (RAG).

**Data dependency:** Existing per-stage forward measures + new backward-rate, time-in-stage, and stall-detection measures. All derivable from current OFH data.

## Tab 4 — Renewals

### Hero (top)
Three cards:
- **Retention rate** (current period, vs target ≥95%)
- **Lost ACV** (this FQ, vs trailing-FQ avg)
- **At-risk renewal ACV** (sum of open Renewal motions in late stages)

### Renewal cohort table (middle)
Renewals due this FQ: Account · ACV · Owner · Stage · Days to close · Status (closed-won / open / lost). Sortable, filterable by region.

### Two side-by-side
- **Renewals MoM trend:** line chart, ACV won by month, last 12 months with target line
- **Lost ACV breakdown:** by reason / by region / by deal-size band (small mark-up table)

### At-risk drilldown (bottom)
Open renewals in late stages with stalled movement or close-date slips: Account · ACV · Owner · Stage · Days stalled · Slip count.

**Data dependency:** existing renewal_retention_rate, lost_arr_quarterly, renewals_mom_trend measures + new "due-to-renew this FQ" denominator (per existing memory item — needs `Renewal_Due_Date__c` or contract-end-date triangulation; if unavailable, fall back to current "Won/(Won+Lost)" formula and footnote).

## Layout standards

- **Tables:** monospace numerics; right-align; RAG colors only on threshold-crossable columns; gray for sub-population caveats; max 7 columns per table
- **Cards:** single number ≥24px; secondary line ≤12px gray; one tertiary metric or sparkline
- **Colors:** RAG = #393 / #d80 / #c33 (green/amber/red); chrome = grays
- **Filters:** persistent left rail (region, motion, FQ); per-tab window slicer at top
- **Empty state:** every table has "No items match current filters" string

## Technical approach (build sequence)

1. **Add backward-rate / time-in-stage / stall measures** to `sm_sales_kpis_rw` via `rw_push_semantic_model.py` (extend existing DAX block — don't replace)
2. **Add window-bound delta measures** for "What Changed" (e.g., `Stage Moves Last 7 Days`, `Slips This FQ`) — also DAX-only, no new tables
3. **Create 4 pages** in `rpt_vp_ops_scorecard` via Fabric REST report.json — extend `rw_add_visual.py` with `--build-page <name>` per tab
4. **Wipe current single-page layout** with `--clear`, then incrementally build each tab
5. **Add table visual schema** to `rw_add_visual.py` — currently only knows cards. Reference: pull a sample report with a table from another workspace (e.g., the SalesManager reference at `/tmp/pbi_ref/`) and decode its table visual JSON.

**Constraints recorded:**
- DAX queryable only via browser today (`executeQueries` REST disabled per `project_rw_dashboard_progress_2026-05-07.md`)
- No PBI Desktop / Windows VM — pure REST + JSON authoring
- Direct Lake auto-refresh on Lakehouse delta updates

## Out of scope (this spec)

- Conditional formatting beyond RAG-on-threshold (Phase 2)
- Drill-through pages (Phase 2 — needs row-context decoded)
- Snapshot history beyond OFH (Phase 2 — would unlock proper "since yesterday" delta on non-tracked fields)
- Renewal "due-to-renew" denominator fix (separate spec — needs SF field decision)
