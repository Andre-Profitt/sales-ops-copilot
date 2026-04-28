# Sales Director Monthly Dashboard — Deep Audit + Rebuild (2026-04-28)

Dashboard ID: `01ZTb00000FSP7hMAH` · Title: "Sales Directors Monthly Pipeline and Insights"

## Audit summary (vs SimCorp Commercial Handbook + ARR/ACV separation memory + _filters.py)

### Critical bugs found (3)

1. **Pipeline Global CFQ** (the hero widget — "Pipeline by Stage")
   was missing `Type IN (Land, Expand)` filter. It summed
   `APTS_Opportunity_ARR__c` across Land/Expand/**Renewal**, blending ARR
   with ACV — same defect as the $466M number from earlier today.
   **Fixed.**
2. **Renewal Pipeline This Quarter** had `RowCount` aggregate only —
   no $ value displayed. **Added** `s!APTS_Renewal_ACV__c.CONVERT`.
3. **SD Win Rate by Stage** filtered on `STAGE_NAME = "7 - Opt Out"` —
   that value **does not exist in this org's picklist** (verified via
   `sf data query GROUP BY StageName`). **Removed** the no-op filter.

### Pollution drift (8 reports)

8 of the 11 underlying reports lacked the canonical owner-based test-bot
exclusion (`FULL_NAME notContain Sabiniewicz`). All 8 patched to add the
filter. The Maria Sabiniewicz test book alone is $16.7M of ARR pollution
per `_filters.py` — including her in dashboard aggregates inflates the
Sales-Director picture by single-digit percent.

### Org-vs-handbook stage drift (informational)

Org's Opportunity.StageName picklist:

| Handbook | Org actual | Records |
|---|---|---|
| 1 - Prospecting | ✓ | 378 |
| 2 - Discovery | ✓ | 795 |
| 3 - Engagement | ✓ | 437 |
| 4 - Shortlisted | ✓ | 107 |
| 5 - Preferred | ✓ | 40 |
| 6 - Contracting | ✓ | 32 |
| **7 - Opt-out** | **MISSING** | 0 |
| 8 - Won | ✓ | 15,615 |
| (n/a) | "0 - Lost" | 9,002 |
| (n/a) | **"0 - No Opportunity"** | **21,605** ← largest single bucket, not in handbook |
| (n/a) | "Quota" | 12 (orphan) |

Worth flagging to whoever owns the Commercial Handbook.

## Rebuild action

**Reports fixed (9 patches via PATCH /analytics/reports):**

| Report ID | Name | Change |
|---|---|---|
| 00OTb000008fBfdMAE | Pipeline Global CFQ | + Type IN (Land,Expand) + pollution |
| 00OTb000008ektxMAA | Renewal Pipeline This Q | + ACV aggregate + pollution |
| 00OTb000008gUrVMAU | SD Win Rate by Stage | drop nonexistent "7 - Opt Out" |
| 00OTb000008fBULMA2 | Renewals By Stage CFQ | rename typo + pollution |
| 00OTb000008Ta9xMAC | Churn Risk | + pollution |
| 00OTb000008aTtJMAU | Approved deals YTD | + pollution |
| 00OTb000008ekp7MAA | Commercial Approval Queue | + pollution |
| 00OTb000008fBEDMA2 | Commercial Approval Current State | + pollution |
| 00OTb000008gUt7MAE | SD Days in Stage | already had pollution (no-op) |

**Dashboard layout (PATCH /analytics/dashboards/01ZTb00000FSP7hMAH):**

- Removed: 1 empty-slot component (reportId=None) + 1 duplicate
  Close Date Slipped YTD widget. Net -2.
- Added 4 new components from the KPI report layer built earlier today:
  - Lost ARR This Q (KPI · `00OTb000008msSvMAI`) — Bar by Stage
  - Pipeline ARR by Owner (KPI · `00OTb000008msPhMAI`) — Bar by Owner
  - New Opps Created Last Month (KPI · `00OTb000008msW9MAI`) — Pie by Type
  - Stage 3+ Opps Created This Month (KPI · `00OTb000008msZNMAY`) — Bar by Stage
- Net: 13 → **15 components**. Well under the 20-widget hard cap. 4 dashboard
  filters (Industry / Legal Country / Sales Region / Account Unit Group)
  preserved through the PATCH per Phase 2.8 memory.

## Verified

- Playwright login + dashboard load: ✓ renders, 4 filters visible, title
  intact. Screenshot at `state/sf_audit/dashboards/sd_monthly_rebuilt.png`
  (gitignored).
- Per Phase 2.8 memory, Lightning UI refresh and dashboard-filter creation
  are not API-automatable. The 9 MD-1 director filter presets per
  `project_sales_director_md1_presets` memory must be configured manually
  in Lightning UI by the dashboard owner.

## Tooling shipped

- `scripts/sf_audit/fix_dashboard_reports.py` — applies the 9 report
  patches (idempotent: re-running is a no-op once fixed)
- `scripts/sf_audit/rebuild_sd_dashboard.py` — applies the dashboard
  components rebuild
- `state/sf_audit/dashboards/sd_monthly_reports_audit.json` — full
  per-report audit data for future reference
