# Sales Ops Dashboards — Audit + Tighten (2026-04-28)

Same audit pattern as the Sales Director Monthly rebuild, applied to:

- **Sales Ops Quarterly KPI Dashboard** (`01ZTb00000FSP9JMAX`)
- **Simcorp Operational Work Dash** (`01ZTb00000FvDSvMAN`)
- **Operational Work Done** (`01ZTb00000FvBZCMA3`)

## Sales Ops Quarterly KPI — biggest cleanup

Pre-state: 15 widgets, **0 dashboard filters**, **0 component-level filterColumns**, 6 of 15 widgets were duplicates (3 pairs), 11 of 12 underlying reports lacked test-pollution exclusion.

**Report fixes (11 patches):**

| Report | Fix |
|---|---|
| Stale Opportunities CFQ | + Type IN (Land,Expand) + pollution |
| High Value Stale Deals | + Type IN (Land,Expand) + pollution |
| Low Probability In Quarter | + pollution |
| No Activity 30+ Days | + pollution |
| Active Opps: No Activity (used 2x) | + pollution |
| Missing Quote Type | + pollution |
| Aging Pipeline 365+ Days | + pollution |
| Land: No Approval Flow | + pollution |
| Missing Amount on Open Opps | + pollution |
| Mid-Stage: No NextStep | + pollution |
| Accounts without KYC Approval | already had account-name pollution (no-op) |

**Dashboard rebuild:**
- Removed 3 duplicate widgets (By Rep dup, Overdue dup, CFY by Owner dup)
- Final count: **15 → 12 widgets**
- Injected the standard 4 filterColumns (Industry / Legal Country / Sales Region / Account Unit Group) into all 11 Opportunity-typed components, so dashboard-level filters (when added in Lightning UI) actually pass through. The Account-typed KYC widget skipped — it doesn't have those columns.

## Operational Work dashboards — light touch only

Both `Simcorp Operational Work Dash` (8 widgets) and `Operational Work Done` (6 widgets) cycle the same 3 reports:
- SC Opportunities Worked On by Person (`00OQA000003msve2AA`)
- Quotes/Proposals Worked On (`00OTb000008JSSDMA4`)
- KYC Approval Status CFY (`00OTb000008KnSzMAK`)

The repetition is **intentional** — each report is shown as Line + Donut + Column visualization variants, not as duplicates.

Note: `Operational Work Done` is a near-subset of `Simcorp Operational Work Dash` (Line + Donut, no Column variants). Possible consolidation candidate — out of scope for this tighten unless requested.

The two non-test reports (`SC Opportunities` + `Quotes/Proposals`) explicitly *include* "Maria Sabiniewicz, Sarah W..." in the `CREATED` filter — that's tracking who did work, NOT the test-pollution context (where her opp book is fixtures). Filter left as-is.

**Single fix applied:** Account-name pollution exclusion on KYC Approval Status CFY (it already had the pattern; no-op confirmation).

## Cumulative session totals on the SF audit work

- Reports patched: **21 unique reports** (across 3 dashboards)
- Dashboards rebuilt: **2 of 3** (SD Monthly + Sales Ops Quarterly KPI)
- Operational Work dashboards: light touch — pollution filter on the one report that needed it; structural rebuild not needed
- Net widget count change:
  - SD Monthly: 13 → 15 (added 4 KPI widgets, removed 1 dup + 1 empty)
  - Sales Ops Quarterly KPI: 15 → 12 (removed 3 duplicate widgets, added filterColumn pass-through)

## What's still on you in Lightning UI

1. Click Refresh on each dashboard once to see updated values flow through
2. Add the 4 dashboard-level filters to **Sales Ops Quarterly KPI** (Industry / Legal Country / Sales Region / Account Unit Group) — pass-through wiring is now in place
3. Configure 9 MD-1 director presets per `project_sales_director_md1_presets` memory on SD Monthly
4. Decide if you want to delete `Operational Work Done` (subset of the Dash version)

Per Phase 2.8 memory: dashboard filter creation + Classic→Lightning save are not API-automatable.
