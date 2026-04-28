# SF Reports — Audit Deployment (2026-04-28)

Native Salesforce reports created by `scripts/sf_audit/reports.py` so the
audit findings are queryable + auditable in-app, not just in our local
markdown.

Org: `simcorp.my.salesforce.com`. Reports live in the running user's
Private folder by default — to share org-wide, create a folder named
"Sales Ops Audit" in Setup → Reports & Dashboards, then re-run the
script (it will detect and place reports there).

## Created reports (5 of 7 attempted)

| Key                     | Lightning URL                                                                | What it surfaces                                                                              |
| ----------------------- | ---------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------- |
| stuck-created-contracts | https://simcorp.my.salesforce.com/lightning/r/Report/00OTb000008ms7xMAA/view | Standard Contract objects in `Status='Created'` for >30d. ~13,904 records — likely abandoned. |
| stale-leads-1y          | https://simcorp.my.salesforce.com/lightning/r/Report/00OTb000008ms9ZMAQ/view | Leads with `LastModifiedDate >1 year`. ~43.6K records (oldest from 2012).                     |
| past-close-open-opps    | https://simcorp.my.salesforce.com/lightning/r/Report/00OTb000008msBBMAY/view | Opps where `IsClosed=false` but `CloseDate < TODAY` — slipped without status update.          |
| stale-open-opps-120d    | https://simcorp.my.salesforce.com/lightning/r/Report/00OTb000008mrn0MAA/view | Open opps with `CreatedDate >120d ago`. KPI median age in this org is 258d (target <120).     |
| missing-email-contacts  | https://simcorp.my.salesforce.com/lightning/r/Report/00OTb000008msCnMAI/view | Contacts where `Email IS NULL`. ~13.7K records — unreachable via email.                       |

## Did not create (2)

| Key                  | Why                                          | Fix                                                                           |
| -------------------- | -------------------------------------------- | ----------------------------------------------------------------------------- |
| bouncing-contacts    | Running user lacks FLS on `EmailBouncedDate` | Setup → Profile → Field Permissions → grant Read on Contact.EmailBouncedDate  |
| owner-inactive-cases | Running user lacks FLS on `OWNER.IsActive`   | Setup → similar; or build a filter on `User.IsActive=false` joined externally |

## Did not attempt — Custom Report Type missing

The two highest-volume audit findings — **74,151 past-due AssetLineItems**
and **17,929 phantom-active assets** — can't have native reports built
because there's no Custom Report Type defined for
`Apttus_Config2__AssetLineItem__c` in this org. The Analytics API
rejects reports against an sObject that has no CRT.

To enable: Setup → Custom Report Types → New →
"Apttus Asset Line Items" with primary object
`Apttus_Config2__AssetLineItem__c`, deploy, then add report defs to
`scripts/sf_audit/reports.py` and re-run.

## Re-creating / iterating

```bash
cd ~/code/apps/sales-ops-copilot
.venv/bin/python -m scripts.sf_audit.reports                  # all
.venv/bin/python -m scripts.sf_audit.reports --only stuck-created-contracts
.venv/bin/python -m scripts.sf_audit.reports --dry-run        # print metadata only
```

Manifest of created IDs/URLs lands in `state/sf_audit/reports_manifest.json`.

The script is idempotent only insofar as SF allows duplicates — running
it twice will create two of each report. Delete the prior batch via the
manifest IDs before re-running.
