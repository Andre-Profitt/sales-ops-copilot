# SF Dashboards Built — Full Inventory (2026-04-28)

11 native Salesforce dashboards in the `Andre` folder
(`00lTb000006OCRBIA4`). All built via the Analytics API. Each
references reports created today via the same API path.

## Tier 1 — Performance / Director Attention

| Dashboard | ID | Widgets | URL |
|---|---|---|---|
| Sales Directors Monthly | 01ZTb00000FSP7hMAH | 20/20 | https://simcorp.lightning.force.com/lightning/r/Dashboard/01ZTb00000FSP7hMAH/view |
| CRO Cockpit | 01ZTb00000FxYZhMAN | 4 | https://simcorp.lightning.force.com/lightning/r/Dashboard/01ZTb00000FxYZhMAN/view |
| Quarter Close Pacing | 01ZTb00000FxYhlMAF | 4 | https://simcorp.lightning.force.com/lightning/r/Dashboard/01ZTb00000FxYhlMAF/view |

## Tier 2 — Sales Ops Attention

| Dashboard | ID | Widgets | URL |
|---|---|---|---|
| Sales Ops Quarterly KPI | 01ZTb00000FSP9JMAX | 18 | https://simcorp.lightning.force.com/lightning/r/Dashboard/01ZTb00000FSP9JMAX/view |
| Activity Health | 01ZTb00000FxYg9MAF | 4 | https://simcorp.lightning.force.com/lightning/r/Dashboard/01ZTb00000FxYg9MAF/view |
| Deal Desk Operations | 01ZTb00000FxYY5MAN | 1 of 4 (FLS-blocked) | https://simcorp.lightning.force.com/lightning/r/Dashboard/01ZTb00000FxYY5MAN/view |

## Tier 3 — Specific Motion / Domain

| Dashboard | ID | Widgets | URL |
|---|---|---|---|
| Renewals | 01ZTb00000FxYTFMA3 | 7 | https://simcorp.lightning.force.com/lightning/r/Dashboard/01ZTb00000FxYTFMA3/view |
| Win/Loss Analysis | 01ZTb00000FxYUrMAN | 6 | https://simcorp.lightning.force.com/lightning/r/Dashboard/01ZTb00000FxYUrMAN/view |
| Marketing & Lead Funnel | 01ZTb00000FxYbJMAV | 5 | https://simcorp.lightning.force.com/lightning/r/Dashboard/01ZTb00000FxYbJMAV/view |
| Forecast Accuracy & Pacing | 01ZTb00000FxYcvMAF | 5 | https://simcorp.lightning.force.com/lightning/r/Dashboard/01ZTb00000FxYcvMAF/view |
| Account Health Watch | 01ZTb00000FxYeXMAV | 4 | https://simcorp.lightning.force.com/lightning/r/Dashboard/01ZTb00000FxYeXMAV/view |

## Conventions baked into every dashboard

- ARR/ACV separation: Land+Expand → APTS_Opportunity_ARR__c, Renewal → APTS_Renewal_ACV__c
- Test pollution exclusion: 9 filter rows mirroring _filters.py (excludes Maria Sabiniewicz $16.7M test book + QtC orgs + named test patterns)
- Currency normalization: .CONVERT suffix on all currency aggregates so multi-currency org sums correctly
- Date scoping: standardDateFilter with THIS_FISCAL_QUARTER / LAST_FISCAL_YEAR / etc.
- Pass-through filterColumns: Industry / Legal Country / Sales Region / Account Unit Group on all Opp-typed widgets
- Auto-laid-out grid: tables full-width, charts half-width, donuts/metrics third-width

## Lightning UI work still on you

1. Refresh each dashboard once
2. Add dashboard-level filters (UI-only per Phase 2.8 memory): Industry / Legal Country / Sales Region / Account Unit Group
3. Move dashboards from Andre folder to a shared "Sales Ops" folder if other directors need access
4. Admin: grant FLS read on `Opportunity.APTS_Opportunity_ARR__c.CONVERT`, `Account.Name`, `OWNER.IsActive`, `EmailBouncedDate` for the dashboard running-user profile to unblock Deal Desk + 2 audit reports

## What the org architecturally can't support yet

- Pipeline Coverage Ratio (no quota source)
- Sales Cycle Trend (no date-diff custom field)
- Phantom-Active Asset reports (no Custom Report Type for Apttus_Config2__AssetLineItem__c)
- Per-director filtered dashboards x9 (filter creation Lightning-UI-only)
