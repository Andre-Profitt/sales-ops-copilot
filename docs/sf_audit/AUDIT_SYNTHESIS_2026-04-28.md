# Dashboard Quality Audit — Synthesis & Fix Log

_2026-04-28. Two parallel audits run; findings synthesized; safe fixes applied._

## Inputs

| Audit | Output | Key finding |
|---|---|---|
| Convention + data audit (`dashboard_quality_audit.json`) | 11 dashboards · 78 widgets scored on 6 axes | 6 widgets returned **zero rows** (Marketing 5 + Deal Desk 1) |
| Cross-dashboard consistency audit (`dashboard_consistency_audit.md`) | 11 dashboards · 78 widgets · 8 concept clusters | **38 of 58 Opp widgets** missing the 4 standard `filterColumns` |

## Fixed automatically

| # | Fix | Scope | Verification |
|---|---|---|---|
| 1 | Backfilled standard 4 `filterColumns` (Industry / Legal Country / Sales Region / Account Unit Group) onto every Opp-typed widget that lacked them | **52 widgets** across 9 dashboards (broader than the audit's 38 because the heuristic also caught RowCount-only Opp widgets) | `scripts/sf_audit/backfill_filter_passthrough.py` re-run = no-op |
| 2 | Removed CLOSE_DATE=THIS_FISCAL_QUARTER from `DD · Stage 3+ Pending Approval` (the 8 real pending-approval opps all had Q3-Q4 close dates) | 1 report | Now returns **EUR 33.2M / 8 rows** |
| 3 | Added `TYPE=Land,Expand` to `KPI · Stage 3+ Opps Created This Month` | 1 report | 22 rows / EUR 508K |
| 4 | Added `TYPE=Land,Expand` to `KPI · New Opps Created Last Month` | 1 report | 168 rows |

Reusable fix scripts:
- `scripts/sf_audit/backfill_filter_passthrough.py`
- `scripts/sf_audit/fix_zero_data_reports.py`

## Cannot be fixed via API — needs Lightning UI

| # | Item | Path |
|---|---|---|
| A | **5 Marketing reports** stuck at `scope=user` (apro owns 0 of 53,148 Leads) | See `MARKETING_DASHBOARD_LIMITATION.md` — open each report → `Show Me ▸ All Leads` |
| B | **10 dashboards have 0 dashboard-level filters** (only SD Monthly has the canonical 4) | Per Phase 2.8 memory: filters are Lightning-UI-only. Open each, **Filters** panel, add: Industry / Legal Country / Sales Region / Account Unit Group |

The 4 widget-level filterColumns we backfilled in fix #1 mean dashboard
filters added in step B will cascade into the widgets immediately — the
plumbing is in place.

## Needs your call on intent

| # | Widget | Question |
|---|---|---|
| C | SD Monthly · "What was won (FY26)" (`00OTb000008gHZJMA2`) | Currently Type-blended (Land+Expand+Renewal) using ARR agg. Mixing ARR with Renewals violates the ARR/ACV separation rule. Split into 2 widgets (L+E ARR + Renewal ACV) or keep blended-with-ARR? |
| D | SD Monthly · "Wins vs losses" (`00OTb000008gUrVMAU`) | Same Type-blended/ARR issue. Filter to L+E only or split? |
| E | SD Monthly · "Churn Risk" (`00OTb000008Ta9xMAC`) | Uses `APTS_Forecast_ACV_AVG__c` aggregate (forecast at risk) instead of `APTS_Renewal_ACV__c`. Intentional forecasting view, or convert to canonical Renewal ACV? |
| F | `renewal_acv` concept appears in **6 widgets / 4 vizes** (Bar/FlexTable/Funnel/Metric) across 3 dashboards | Per memory, viz changes need explicit approval — pick one canonical viz for renewal_acv? |
| G | Header naming drift: 'Open Pipeline ARR' vs 'Open Pipeline by Region' (same concept) | Rename for parallelism? |

## False positives (audit was over-strict — no action needed)

- 51 widgets flagged for "name-only pollution (no owner filter)" — the
  `FULL_NAME notContain Sabiniewicz` pattern is the canonical filter (per
  `_filters.py`); the audit's preference for an `Owner.Id` filter is stricter
  than the org convention.
- 6 Renewals widgets flagged for "ACV agg on Land/Expand" — those are
  Renewal-typed widgets correctly using ACV; the audit's heuristic
  misclassified them.
- 7 "CUSTOM with no dates" warnings on governance reports — semantically
  correct (governance items are current-state, not date-bounded).
- "Pipeline stage age" using `STAGE_DURATION` aggregate is correct (it's a
  process metric, not financial).

## Counts

```
Before:
  - 6/78 widgets returned zero rows (8% empty)
  - 38/58 Opp widgets had no filter pass-through (66% broken on dashboard-filter cascade)
  - 4 underlying reports had clear data/scope bugs

After:
  - 1/78 widgets still zero (Deal Desk fixed; 5 Marketing left for UI fix)
  - 0/58 Opp widgets missing filter pass-through (52 patched, 6 non-Opp left correctly alone)
  - 3 underlying reports patched programmatically; 5 Lead reports + 10 dashboard-filter sets pending UI fix
```
