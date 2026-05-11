# RW Zebra BI GraphRAG element map - 2026-05-09

Purpose: convert the Zebra BI template catalog into a concrete RW VP Ops design
pull-list. This is not a generic inspiration board; it maps downloaded PBIX
template elements to RW tabs, fields, and measures.

## Download + extraction

Local artifact root:

`/Users/test/Downloads/rw-zebra-bi-template-research-20260509/`

Downloaded:

- 21 Zebra BI Power BI template pages.
- 20 direct PBIX zip downloads, 169 MB total.
- The marketing performance page did not expose a direct PBIX zip in page HTML.
- PBIX internals were readable for all downloaded files.

Generated analysis files:

- `analysis/template_summary.csv` - per-template page and visual counts.
- `analysis/page_visual_summary.csv` - per-page visual counts.
- `analysis/visual_inventory.csv` - 1,729 visual rows with visual type,
  position, text, and projection roles.
- `analysis/graph_nodes.jsonl` - 2,438 graph nodes.
- `analysis/graph_edges.jsonl` - 6,209 graph edges.
- `analysis/rw_candidate_elements.json` - ranked RW candidate elements.

Extracted Zebra visual inventory across all downloaded PBIX files:

| Visual family | Count | RW interpretation |
| --- | ---: | --- |
| Zebra BI Tables | 146 | Best source for consultant-grade table/chart hybrids |
| Zebra chart / waterfall visuals | 140 | Best source for bridges, trends, and variance explanations |
| Zebra BI Cards | 74 | Use sparingly for KPI pulse rows, not card walls |
| Native slicers | 426 | Templates rely heavily on controlled filter strips |
| Textboxes | 263 | Use for page titles and narrative labels only |

## Source template ranking for RW

| Rank | Template | Best RW use | Why |
| ---: | --- | --- | --- |
| 1 | Sales Funnel Power BI Template | Stage Hygiene, Forecast | Closest domain match: sales stages, conversion, funnel health, plan/forecast variance |
| 2 | Sales Dashboard in Power BI Template | VP Ops Scorecard | Strongest executive landing-page pattern: KPI pulse, Top N, waterfall/variance |
| 3 | Daily Sales Flash | What Changed | Best operating-cadence pattern for daily/weekly deltas |
| 4 | SaaS Sales Dashboard | Renewals, Growth Mix | Useful recurring-revenue grammar, but ACV/ARR split must be enforced |
| 5 | Price-Volume-Mix Variance | Growth Mix | Best contribution-bridge grammar for Land vs Expand vs source/partner mix |
| 6 | Dynamic Comments | Later annotation layer | Useful after we have a comments table keyed by KPI/period/segment |

## Exact elements to pull

### 1. Stage Hygiene - Zebra BI Tables proof

Source: `sales-funnel-power-bi-template`, pages `Home 3`, `DT - GEO`,
`DT - GEO %`.

Template pattern:

- Zebra BI Tables with `Category` hierarchy and multiple `Values`.
- Sales funnel page uses Zebra Cards, Zebra Tables, and waterfall/column visuals.
- Detail pages use Zebra Tables as the primary drill surface.

RW element:

- `Stage x Motion Hygiene` table with embedded bars and variance notation.

Bindings:

- Category: `f_stage_transition[from_stage_name]`,
  `f_stage_transition[to_stage_name]`
- Values:
  - `Stage Forward Pct (LE)`
  - `Stage Backward Pct (LE)`
  - `Avg Days In Prior Stage (LE)`
  - `Total Stage Transitions`
  - `Stage Moves ARR FQTD`
- Comparison/plan target to add:
  - `Stage Forward Target = 70%`
  - prior-period `Stage Forward Pct (LE)`

Why first: this gives the most visible jump from basic Power BI to
consulting-grade reporting without relying on more colored cards.

### 2. VP Ops Scorecard - exception table, not RAG cards

Source: `sales-dashboard-power-bi-template`, page `Landing`.

Template pattern:

- Zebra BI Tables with roles:
  - `Category`
  - `Values`
  - `PreviousYear`
  - `Plan`
  - `Group`
- Landing page also uses waterfall and Cards, but the table pattern is the
  cleanest RW fit.

RW element:

- `Exception ARR by Region` executive object.

Bindings:

- Category: `d_region[region]`
- Values:
  - `Exception ARR`
  - `Exception Opps Count`
  - `At Risk Opps ARR`
  - `Watch Opps ARR`
- Comparison/plan target to add:
  - prior-period `Exception ARR`
  - exception threshold measure

Rule: keep this ARR-only for Land + Expand. Do not mix Renewal ACV into this
element.

### 3. VP Ops Scorecard - compact KPI pulse row

Source: `sales-funnel-power-bi-template`, page `Home`.

Template pattern:

- Zebra BI Cards roles:
  - `Category`
  - `Group`
  - `Values`
  - `Plan`
  - `Forecast`

RW element:

- One compact KPI pulse row, not individual decorative panels.

Bindings:

- Category: `d_calendar[fiscal_quarter]`
- Values:
  - `Total Closed Won ARR`
  - `Win Rate ARR`
  - `Stage Forward Pct (LE)`
  - `Renewal Retention Pct (Period)`
- Plan/target:
  - `Closed Won ARR LY`
  - win-rate target 25%
  - stage-forward target 70%
  - renewal-retention target 95%

Constraint: if Zebra Cards clip text or force oversized spacing, skip them and
use Zebra Tables instead.

### 4. What Changed - Daily Sales Flash ledger

Source: `daily-sales-flash-power-bi-dashboard`, pages `Overview`,
`Sales Details`, `Returns Details`.

Template pattern:

- Zebra BI Tables with period columns like previous week, actual, delta, 7D,
  MTD, plan, and end-of-month outlook.

RW element:

- Movement ledger by change class, account, and opportunity.

Bindings:

- Category:
  - `f_opportunity[account_name]`
  - `f_opportunity[opportunity_name]`
- Values:
  - `Stage Moves ARR 1d`
  - `Stage Moves ARR 7d`
  - `New Opps Count 7d`
  - `Closed Won Count 7d`
  - `Closed Lost Count 7d`
  - `Backward Moves Count 7d`

Need: add/confirm prior-day and prior-week delta measures before using the full
Daily Sales Flash period-column pattern.

### 5. Forecast - funnel variance trend

Source: `sales-funnel-power-bi-template`, pages `Home`, `Home 2`.

Template pattern:

- Zebra chart/waterfall visuals with:
  - `Category = Calendar.Month`
  - `Values = actual`
  - `Plan`
  - `Forecast`

RW element:

- Open pipeline vs closed-won/forecast trend.

Bindings:

- Category: `d_calendar[year_month]`
- Values:
  - `Total Closed Won ARR`
  - `Total Open Pipeline ARR`
  - `Pipeline ARR LY`
  - `Pipeline ARR YoY Pct`

Blocker: true plan/forecast comparison needs quota or forecast snapshot data.
Do not fake plan semantics with arbitrary thresholds.

### 6. Renewals - ACV-only recurring revenue pattern

Source: `saas-sales-power-bi-dashboard-template`, pages `Overview`,
`MRR Trends`, `MRR by Customers`.

Template pattern:

- Recurring revenue trend, churn/new movement, Top N customers, benchmark by
  owner/segment.

RW element:

- Renewal ACV retention and loss explanation.

Bindings:

- Category:
  - `d_calendar[fiscal_quarter]`
  - `d_account[account_name]`
- Values:
  - `Renewal Retention Pct (Period)`
  - `Total Renewal ACV Won`
  - `Total Renewal ACV Lost`
  - `Renewal ACV YTD YoY Pct`
- Plan/target:
  - retention target 95%
  - prior-period Renewal ACV

Rule: label this Renewal ACV only. Do not use SaaS template ARR/MRR language
where it implies blending.

### 7. Growth Mix - contribution bridge

Source: `price-volume-mix-analysis-power-bi-template`, pages `PVM +
explanations`, `PVM hierarchy`.

Template pattern:

- Contribution bridge by category plus supporting detail table.
- Waterfall and Zebra Tables with category hierarchy.

RW element:

- Land vs Expand vs partner/source contribution bridge.

Bindings:

- Category:
  - `f_opportunity[motion_type]`
  - `f_opportunity[lead_source]`
  - `d_region[region]`
- Values:
  - `Land Closed Won ARR`
  - `Expand Closed Won ARR`
  - `Partner ARR`
  - `Partner Pct`
  - `Source ARR Won`
  - `Source Win Rate`

Need: prior-period ARR by motion/source for meaningful variance.

### 8. Dynamic comments - later annotation layer

Source: `dynamic-comments-power-bi-template`, page `Zebra BI comments from
model`.

Template pattern:

- Zebra visuals bind `Comments` or `Tooltips` to a comment field:
  `Min(Comments.Comment)`.

RW element:

- Data-driven executive annotations by KPI, period, region, and motion.

Need:

- A small comments table keyed by:
  - `kpi_key`
  - `period_key`
  - `region`
  - `motion_type`
  - `comment`

This is high leverage, but it should come after the first Zebra Table proof.

## Build order

1. Install/activate Zebra visuals in the lab PBIP.
2. Build `Stage x Motion Hygiene` as the first Zebra BI Tables visual.
3. Build `Exception ARR by Region` as the second Zebra BI Tables visual.
4. Test Zebra Cards only after Tables render cleanly.
5. Save the lab PBIP and compare Desktop render against the live native report.
6. Promote no Zebra visual to production until Fabric renders it correctly.

## Style rules pulled from the templates

- Lead with one business message, not a decorative title.
- Use tables with embedded bars and variance notation for dense executive
  surfaces.
- Use red/green as variance semantics only, not as colored dashboard panels.
- Keep Cards grouped and narrow; never rebuild a wall of KPI boxes.
- Use Top N + Others for region/customer/deal lists instead of long raw tables.
- Use dynamic comments only when they are data-bound and update with filters.

## Non-negotiable RW rule

ARR and ACV stay separate:

- ARR = Land + Expand via ARR measures.
- ACV = Renewal via ACV measures.
- `Total Open Pipeline Value` is the only cross-motion measure, and only when
  explicitly labeled.
