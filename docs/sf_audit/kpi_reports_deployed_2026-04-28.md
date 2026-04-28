# SF KPI Reports — Deployment (2026-04-28)

Native Salesforce reports for the executable KPIs from the RW/AP framework
workbook. Created by `scripts/sf_audit/kpi_reports.py`. Live in the running
user's Private folder until the "Sales Ops Audit" folder exists in Setup.

## Conventions baked in

- **ARR/ACV separation** per `feedback_simcorp_arr_acv_separation` memory:
  Land/Expand → `Opportunity.APTS_Opportunity_ARR__c.CONVERT` (currency-converted)
  Renewal → `Opportunity.APTS_Renewal_ACV__c.CONVERT`. Never blended.
- **Date scoping**: `standardDateFilter` with `THIS_FISCAL_QUARTER` (matches
  brief.py canonical convention).
- **Test pollution exclusion**: 9 filter rows mirroring `_filters.py` —
  excludes Maria Sabiniewicz's 43 test opps ($16.7M), QtC test orgs, ASH
  Dummy / SBL Opp / Back Office / Generic q* / To Be Deleted / TEST patterns.

## Created reports

| Key | URL | What |
|---|---|---|
| kpi-pipeline-by-stage | TBD | Open L+E ARR sum by Stage, current quarter — should match $27.7M baseline |
| kpi-pipeline-by-owner | TBD | Same data grouped by Owner — concentration risk |
| kpi-closed-won-quarter | 00OTb000008msRJMAY | Won L+E bookings this quarter, by Owner |
| kpi-lost-arr-quarter | 00OTb000008msSvMAI | Lost L+E ARR this quarter, by Stage |
| kpi-renewal-pipeline-acv | 00OTb000008msUXMAY | Open Renewal ACV this quarter (separate from ARR!) |
| kpi-new-opps-last-month | 00OTb000008msW9MAI | New opps created last month, by Type |
| kpi-win-loss-this-q | 00OTb000008msXlMAI | Closed L+E grouped by IsWon — for win-rate read |
| kpi-stage3-approvals-this-month | 00OTb000008msZNMAY | Stage 3+ opps created last month |

(Full IDs in `state/sf_audit/kpi_reports_manifest.json`.)

## Re-running

```bash
python3 -m scripts.sf_audit.kpi_reports                # all 8
python3 -m scripts.sf_audit.kpi_reports --only kpi-renewal-pipeline-acv
python3 -m scripts.sf_audit.kpi_reports --dry-run
```

## What the layer covers vs what it doesn't

**Covered (8 KPIs natively in SF):**
- Open pipeline by stage + owner
- Won/lost ARR this quarter
- Renewal pipeline ACV
- New opps velocity
- Win-rate composition
- Stage 3+ governance volume

**NOT covered (still need work):**
- Sales Cycle Length (avg days closed_won) — needs custom date-diff field
- Median Opportunity Age — SF reports don't natively support median, only avg
- Lead → Opp Time / Win/Loss — Lead conversion analytics need a different report type (LeadHistory or similar)

These remaining KPIs still get computed in `scripts/sf_audit/kpi.py` against
the workbook output (`reports/kpi_values_<date>.xlsx`) — just not as native
SF reports yet.
