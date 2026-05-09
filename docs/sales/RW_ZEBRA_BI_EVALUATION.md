# RW Zebra BI evaluation - 2026-05-09

Goal: test Zebra BI in a sandbox before moving any RW VP Ops report page to
production. The problem to solve is not color polish; it is replacing
AI-looking Power BI card walls with a restrained IBCS-style executive reporting
pattern.

## Current sandbox

Local PBIP lab copy:

`~/Downloads/rw-pbi-format-lab/rpt_vp_ops_scorecard_zebra_lab_20260509_pbip/rpt_vp_ops_scorecard_zebra_lab.pbip`

Do not save Zebra experiments into the live PBIP until the lab page passes
visual review.

Windows auth state:

- Company Portal now opens under SimCorp after re-registering
  `Microsoft.AAD.BrokerPlugin`.
- Power BI Desktop is signed in as Andre.
- Use the lab PBIP for Zebra install/license testing.

## Source read

- Zebra BI has three Power BI visuals: Tables, Charts, Cards. Zebra says they
  install from AppSource and are Microsoft-certified; Charts and Tables are also
  IBCS-certified.
  <https://help.zebrabi.com/kb/power-bi/overview/>
- Initial setup is: Visualizations pane `...` -> Get more visuals -> search
  `Zebra` -> add Tables, Charts, Cards. License activation is done from the
  Zebra logo/info button inside each visual.
  <https://help.zebrabi.com/kb/power-bi/initial-setup-guide/>
- Zebra BI Tables are the strongest fit for RW detail surfaces: comparison
  tables, embedded charts, automatic variance, hierarchy, Top N + Others, and
  up to 20 additional measures.
  <https://help.zebrabi.com/kb/power-bi/overview-of-the-zebra-bi-tables-visual/>
- Zebra BI Charts support column/bar, line, waterfall, variance, combo charts,
  forecast segments, and small multiples.
  <https://help.zebrabi.com/kb/power-bi/overview-of-chart-types-in-the-zebra-bi-charts-visual/>
- Zebra BI Cards support KPI rows/cards with comparisons, trend/category fields,
  scaled groups, drill-through, focus mode, tooltips, and dynamic comments.
  <https://help.zebrabi.com/kb/power-bi/getting-started-with-zebra-bi-cards/>

## Best Zebra templates for RW

### 1. Sales Funnel Power BI Template - primary reference

Best fit for RW because it is pipeline-stage and RevOps oriented. It explicitly
covers funnel bottlenecks, stage conversion, pipeline health, forecast variance,
and executive revenue opportunity review.

Use for:

- `Stage Hygiene`: stage conversion table/chart, bottleneck readout, stage
  leakage.
- `Forecast`: pipeline vs forecast/plan variance, stage-weighted value.
- `VP Ops Scorecard`: one clean "where are we losing revenue?" funnel block.

Source:
<https://zebrabi.com/template/sales-funnel-power-bi-template/>

### 2. Sales Dashboard in Power BI Template - executive page reference

Best fit for the home/front page. It uses revenue/conversion KPI cards,
variance waterfalls, Top N rankings, time/region filters, and dynamic comments.
The useful pattern is a single executive landing page plus drillable sections,
not many equal-weight cards.

Use for:

- `VP Ops Scorecard`: KPI strip + one variance/driver visual + one Top N table.
- `Growth Mix`: top/bottom contributors by region, lead source, product motion,
  or account manager.

Source:
<https://zebrabi.com/template/sales-dashboard-power-bi-template/>

### 3. Daily Sales Flash - daily operating cadence reference

Best fit for "What Changed." It is built around a daily, weekly, monthly
readout with deeper detail pages. That maps better to RW's morning operating
review than a generic scorecard.

Use for:

- `What Changed`: since yesterday / this week / FQTD selector.
- Daily exception readout: slipped, stalled, forward-moved, won/lost.

Source:
<https://zebrabi.com/template/daily-sales-flash-power-bi-dashboard/>

### 4. SaaS Sales Power BI Dashboard - selective reference

Useful only for recurring-revenue patterns: ARR/MRR growth, churn/retention,
cohorts, Top N customers, and dynamic comments. Do not copy the SaaS framing
blindly; SimCorp has Land, Expand, and Renewal motions with ARR/ACV separation.

Use for:

- `Renewals`: retention / churn-style ACV risk patterns.
- `Growth Mix`: ARR expansion, SaaS-motion growth, Top N customer/product
  analysis.

Source:
<https://zebrabi.com/template/saas-sales-power-bi-dashboard-template/>

## Recommended RW Zebra page architecture

### VP Ops Scorecard

Target: 4-5 objects, no card wall.

- Zebra BI Cards in row layout:
  - Exception ARR
  - Exception Opps Count
  - Won ARR
  - Win Rate
  - Stage Forward %
  - Renewal Retention
- Zebra BI Charts:
  - Exception ARR by Region as Top N + Others.
  - Open Pipeline Value by Stage as bar or waterfall-style contribution.
- Zebra BI Tables:
  - Deal inspection queue with text columns and Open Value integrated bars.

### What Changed

- Zebra BI Cards:
  - At Risk / Watch / Healthy as one grouped KPI visual, not three panels.
- Zebra BI Charts:
  - Stage moves / slipped / new / closed as a contribution or small-multiple
    view once snapshot measures are stable.
- Zebra BI Tables:
  - Top changes by ARR impact with change class and Salesforce URL.

### Forecast

- Zebra BI Cards:
  - Closed Won ARR, Open Pipeline ARR, Win Rate, Days Remaining.
- Zebra BI Tables:
  - Stage x Motion with Open Value and weighted/forecast columns.
- Zebra BI Charts:
  - Open pipeline vs prior year / forecast where comparison measures exist.

### Stage Hygiene

- Zebra BI Tables first:
  - Stage transition matrix with Forward %, Backward %, Avg Days, Open Count,
    Open ARR.
- Zebra BI Charts:
  - Stage conversion bottleneck chart / waterfall.

### Renewals

- Zebra BI Cards:
  - Renewal Retention, Won ACV, Lost ACV, At-risk Renewal ACV.
- Zebra BI Tables:
  - Renewal cohort / at-risk renewal queue.
- Zebra BI Charts:
  - Renewal ACV trend, lost/won variance.

## Lab proof gate

Before promoting Zebra to production, prove these in the lab PBIP:

1. AppSource install works for `Zebra BI Tables`, `Zebra BI Charts`, and
   `Zebra BI Cards`.
2. License activates once per visual family.
3. A Zebra BI Table can bind to the existing live model fields:
   `stage_name`, `motion_type`, `Total Open Pipeline Value`.
4. A Zebra BI Chart can bind to:
   `d_region[region]` + `Exception ARR`.
5. A Zebra BI Cards visual can bind to the KPI pulse measures without clipping.
6. Save PBIP, then run:
   `python3 -m scripts.sales.rw_dashboard_harness diff --before <snapshot> --after <lab-report-json> --emit-candidates`
7. Screenshot review passes:
   - no cut-off text
   - no decorative RAG card wall
   - EUR labels
   - clear page hierarchy
   - ARR and ACV not blended except explicitly labeled `Total Open Pipeline Value`

## Data/model prep likely needed

Zebra is most powerful when it has Actual / PY / Plan / Forecast comparison
slots. RW currently has some LY and YoY measures, but not quota/plan. The
minimum useful semantic additions are:

- Target / threshold measures for:
  - Win Rate target 25%
  - Stage Forward target 70%
  - Renewal Retention target 95%
  - Coverage target 3x, once quota exists
- Previous-period measures for:
  - Exception ARR
  - Open Pipeline ARR
  - Renewal ACV Won
  - Stage Forward %
- Text/comment table later for Zebra dynamic comments, if we want annotated
  executive explanations.

## Decision

Use Zebra BI if the lab proves stable. The best RW pattern is:

1. Sales Funnel template logic for pipeline/stage pages.
2. Sales Dashboard template logic for the VP Ops front page.
3. Daily Sales Flash logic for What Changed.
4. SaaS Sales logic only for renewal/ARR growth sections.

Do not port the current native card layout directly into Zebra. Use Zebra to
reduce visual count and create chart/table-first business notation.
